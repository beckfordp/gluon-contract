# SPDX-License-Identifier: MIT

"""Checks a notification-service capture on its own (gluon PLAN.md RPN-1).

The capture (`contracts/notification-service/<date>/`, made on the laptop by
its `CAPTURE.sh`) is the Rust port's reference, so it is checked before
anything is compared with it:
- every `http/*.txt` is a `curl -si` exchange; the timed health files
  (CAPTURE.sh step 9) end with curl's `elapsed=`/`curl_exit=` trailer and hold
  a response, or nothing when curl timed out (exit 28);
- every `otlp/*.pb` decodes, and its `.json` beside it (OTLP/JSON, written by
  `decode-otlp`) gives the same spans;
- every `.jsonl` line is JSON;
- each `kafka/<topic>-dlq.txt` holds exactly the scenario table's dead letters;
- `db/sent-email.jsonl` is exactly the scenario table's rows (`ns_scenarios`).

Each check is pure and returns problems naming the file relative to the
capture; `check_capture` reads a directory and runs them all. Only what these
checks define is a problem; anything else (a missing file, bytes that aren't
UTF-8, a `.pb` `decode-otlp` can't read) raises, as reading user-service's
capture does (`capture.capture_file`, `capture.load_exchange`). Usage:

    python -m gluon_contract.ns_capture check [DIR]        # PASS, or FAIL and exit 1
    python -m gluon_contract.ns_capture decode-otlp [DIR]  # write otlp/*.json

DIR defaults to the latest notification-service capture.
"""

import argparse
import base64
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from google.protobuf import json_format
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

from gluon_contract.capture import CaptureError, parse_exchange
from gluon_contract.cluster import parse_console_line
from gluon_contract.contracts import CONTRACTS_ROOT, latest_capture
from gluon_contract.ns_scenarios import (
    TOPICS,
    envelope_field,
    expected_dead_letters,
    expected_rows,
)
from gluon_contract.otlp import OtlpDecodeError, Span, decode_traces

SERVICE = "notification-service"

TIMED_EXCHANGES = frozenset(
    f"http/{name}.txt"
    for name in (
        "health-ready-pg-paused",
        "health-pg-paused",
        "health-ready-pg-back",
        "health-ready-pg-stopped",
        "health-ready-pg-restarted",
    )
)
"""CAPTURE.sh step 9's `timed` files: readiness with Postgres paused, back, stopped, restarted."""

CURL_TIMEOUT = 28
"""curl's exit code when `-m` runs out (CAPTURE.sh: 20 s)."""
TRAILER = re.compile(rb"\n--\nelapsed=[0-9.]+s\ncurl_exit=(\d+)\n?\Z")
"""What `timed` appends: curl's `-w` output, then its exit code."""
CONSOLE_RECORD = re.compile(r"CreateTime:\d+\t(?P<rest>[^\t]*\t[^\t]*\t.*)\Z", re.DOTALL)
"""A console-consumer line with `print.timestamp`, `print.headers` and `print.key`."""

PROTOBUF = "application/x-protobuf"
OTLP_JSON = "application/json"
ID_FIELDS = ("traceId", "spanId", "parentSpanId")


@dataclass(frozen=True, slots=True)
class Problem:
    """Something wrong with a capture file."""

    file: str
    """Relative to the capture, e.g. `http/health.txt`."""
    message: str


@dataclass(frozen=True, slots=True)
class FileResult:
    """One file checked, and what was wrong with it (nothing, when it passed)."""

    file: str
    problems: tuple[Problem, ...]


# --- http/*.txt -----------------------------------------------------------------


def check_exchange(file: str, raw: bytes) -> list[Problem]:
    """A `curl -si` output parses as an exchange; a timed one may be only curl's timeout."""
    if file in TIMED_EXCHANGES:
        trailer = TRAILER.search(raw)
        if trailer is None:
            return [
                Problem(
                    file,
                    "no curl trailer (elapsed=…s, curl_exit=…) on a timed exchange "
                    "(CAPTURE.sh step 9)",
                )
            ]
        raw, curl_exit = raw[: trailer.start()], int(trailer.group(1))
        if curl_exit == CURL_TIMEOUT and not raw.strip():
            return []
        if curl_exit not in (0, CURL_TIMEOUT):
            return [
                Problem(
                    file,
                    f"curl_exit={curl_exit}: expected 0 (a response) or "
                    f"{CURL_TIMEOUT} (curl's timeout)",
                )
            ]
    try:
        parse_exchange(raw)
    except CaptureError as error:
        return [Problem(file, str(error))]
    return []


# --- otlp/*.pb and *.json -----------------------------------------------------------


def otlp_to_json(pb: bytes) -> str:
    """A protobuf trace export as readable OTLP/JSON: lowerCamelCase fields, hex ids,
    integer enums, 2-space indent (what `decode_traces` reads as `application/json`).

    Raises:
        google.protobuf.message.DecodeError: when `pb` is no export.
    """
    request = ExportTraceServiceRequest.FromString(pb)
    document = json_format.MessageToDict(request, use_integers_for_enums=True)
    for resource_spans in document.get("resourceSpans", []):
        for scope_spans in resource_spans.get("scopeSpans", []):
            for span in scope_spans.get("spans", []):
                _base64_ids_to_hex(span)
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def _base64_ids_to_hex(item: dict[str, object]) -> None:
    """proto3's JSON mapping writes bytes as base64; OTLP/JSON ids are hex."""
    for field in ID_FIELDS:
        if value := item.get(field):
            item[field] = base64.b64decode(str(value)).hex()


def check_otlp_export(pb_file: str, pb: bytes, json_body: bytes | None) -> list[Problem]:
    """The export decodes, and its `.json` (None: missing) decodes to the same spans."""
    json_file = pb_file.removesuffix(".pb") + ".json"
    try:
        spans = decode_traces(pb, PROTOBUF)
    except OtlpDecodeError as error:
        return [Problem(pb_file, str(error))]
    if json_body is None:
        return [
            Problem(
                json_file,
                f"missing: decode {pb_file} with `python -m gluon_contract.ns_capture decode-otlp`",
            )
        ]
    try:
        json_spans = decode_traces(json_body, OTLP_JSON)
    except OtlpDecodeError as error:
        return [Problem(json_file, str(error))]
    if json_spans != spans:
        return [
            Problem(
                json_file,
                f"spans differ from {pb_file}: expected {_summary(spans)}, "
                f"got {_summary(json_spans)}",
            )
        ]
    return []


def _summary(spans: Sequence[Span]) -> str:
    return f"{len(spans)} span(s) {[span.name for span in spans]}"


# --- *.jsonl --------------------------------------------------------------------------


def check_jsonl(file: str, text: str) -> list[Problem]:
    """Every line is one JSON value."""
    problems = []
    for number, line in enumerate(text.splitlines(), start=1):
        try:
            json.loads(line)
        except ValueError as error:
            problems.append(Problem(file, f"line {number} is not JSON ({error}): {line[:80]!r}"))
    return problems


# --- kafka/*-dlq.txt ---------------------------------------------------------------------


def check_dead_letters(file: str, topic: str, text: str) -> list[Problem]:
    """The DLQ of input `topic` holds exactly the table's dead letters, in order:
    the same key, and the same event id (or raw value, for no envelope)."""
    expected = [
        (scenario.key, scenario.event_id or scenario.raw_value)
        for scenario in expected_dead_letters(topic)
    ]
    actual: list[tuple[str | None, str | None]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        record = CONSOLE_RECORD.match(line)
        if record is None:
            return [
                Problem(
                    file,
                    f"line {number} is no console-consumer record "
                    f"(CreateTime:…, headers, key, value; tab-separated): {line[:80]!r}",
                )
            ]
        parsed = parse_console_line(f"{topic}-dlq", record.group("rest"))
        actual.append((parsed.key, envelope_field(parsed.value, "eventId") or parsed.value))
    if actual != expected:
        return [
            Problem(
                file,
                f"dead letters (key, event id or raw value) differ: expected {expected}, "
                f"got {actual}",
            )
        ]
    return []


# --- db/sent-email.jsonl -------------------------------------------------------------------


TIMESTAMP_SET_BY_STATUS: Mapping[str, tuple[str, ...]] = {
    "sent": ("sent_at",),
    "failed": ("failed_at",),
}
"""Which of `sent_at`/`failed_at` a row of each status has set; the other stays null."""


def check_sent_email(file: str, text: str) -> list[Problem]:
    """The rows are exactly the table's, one per source event, in any order: every
    column but `id`, `body` and the timestamps, and `sent_at`/`failed_at` as the
    status says."""
    expected = {row.source_event_id: row for row in expected_rows()}
    seen: set[str] = set()
    problems = []
    for number, line in enumerate(text.splitlines(), start=1):
        try:
            document = json.loads(line)
        except ValueError:
            problems.append(Problem(file, f"line {number} is not JSON: {line[:80]!r}"))
            continue
        actual: dict[str, object] = document if isinstance(document, dict) else {}
        event = str(actual.get("source_event_id"))
        if event in seen:
            problems.append(Problem(file, f"line {number}: a second row for event {event}"))
            continue
        seen.add(event)
        row = expected.get(event)
        if row is None:
            problems.append(
                Problem(file, f"line {number}: a row for event {event}, not in the scenario table")
            )
            continue
        differences = [
            f"{column}: expected {value!r}, got {actual.get(column)!r}"
            for column, value in asdict(row).items()
            if actual.get(column) != value
        ]
        set_columns = TIMESTAMP_SET_BY_STATUS.get(row.status, ())
        differences += [
            f"{column}: expected {'a time' if column in set_columns else 'null'} "
            f"for status {row.status!r}, got {actual.get(column)!r}"
            for column in ("sent_at", "failed_at")
            if (actual.get(column) is not None) != (column in set_columns)
        ]
        if differences:
            problems.append(
                Problem(file, f"event {event} ({row.event_type}): {'; '.join(differences)}")
            )
    missing = [event for event in expected if event not in seen]
    if missing:
        problems.append(Problem(file, f"no row for event(s) {', '.join(missing)}"))
    return problems


# --- A capture directory --------------------------------------------------------------------


def check_capture(directory: Path) -> list[FileResult]:
    """Runs every check over the capture in `directory`, one result per file read.

    Raises:
        FileNotFoundError: when a DLQ dump or `db/sent-email.jsonl` is missing.
    """
    results: list[FileResult] = []

    def add(file: str, problems: Sequence[Problem]) -> None:
        results.append(FileResult(file, tuple(problems)))

    def relative(path: Path) -> str:
        return path.relative_to(directory).as_posix()

    for path in sorted((directory / "http").glob("*.txt")):
        add(relative(path), check_exchange(relative(path), path.read_bytes()))
    otlp = directory / "otlp"
    for path in sorted(otlp.glob("*.pb")):
        json_path = path.with_suffix(".json")
        json_body = json_path.read_bytes() if json_path.is_file() else None
        add(relative(path), check_otlp_export(relative(path), path.read_bytes(), json_body))
    for path in sorted(otlp.glob("*.json")):
        if not path.with_suffix(".pb").is_file():
            add(relative(path), [Problem(relative(path), "no .pb export beside it")])
    for path in sorted(directory.rglob("*.jsonl")):
        add(relative(path), check_jsonl(relative(path), path.read_text(encoding="utf-8")))
    for topic in TOPICS:
        file = f"kafka/{topic}-dlq.txt"
        add(file, check_dead_letters(file, topic, (directory / file).read_text(encoding="utf-8")))
    file = "db/sent-email.jsonl"
    add(file, check_sent_email(file, (directory / file).read_text(encoding="utf-8")))
    return results


def write_otlp_json(directory: Path) -> list[Path]:
    """Writes each `otlp/*.pb`'s OTLP/JSON beside it; returns the files written.

    Raises:
        google.protobuf.message.DecodeError: for an export that doesn't decode.
    """
    written = []
    for path in sorted((directory / "otlp").glob("*.pb")):
        json_path = path.with_suffix(".json")
        json_path.write_text(otlp_to_json(path.read_bytes()), encoding="utf-8")
        written.append(json_path)
    return written


def main(argv: Sequence[str]) -> int:
    """`check [DIR]` or `decode-otlp [DIR]`; returns the exit code."""
    parser = argparse.ArgumentParser(
        prog="python -m gluon_contract.ns_capture",
        description="Check a notification-service capture, or decode its OTLP exports.",
    )
    parser.add_argument("command", choices=("check", "decode-otlp"))
    parser.add_argument(
        "capture",
        nargs="?",
        type=Path,
        help="the capture directory (default: the latest notification-service capture)",
    )
    args = parser.parse_args(argv)
    given: Path | None = args.capture
    directory = given if given is not None else latest_capture(CONTRACTS_ROOT, SERVICE)
    if not directory.is_dir():
        print(f"FAIL: {directory} is not a directory")
        return 1
    if args.command == "decode-otlp":
        for path in write_otlp_json(directory):
            print(f"wrote {path.relative_to(directory).as_posix()}")
        return 0
    results = check_capture(directory)
    problems = [problem for result in results for problem in result.problems]
    for result in results:
        if not result.problems:
            print(f"ok   {result.file}")
        for problem in result.problems:
            print(f"FAIL {problem.file}: {problem.message}")
    if problems:
        print(f"FAIL: {len(problems)} problem(s) in {directory}")
        return 1
    print(f"PASS: {directory} checked ({len(results)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
