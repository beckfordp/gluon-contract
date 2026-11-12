# SPDX-License-Identifier: MIT

"""Checking a notification-service capture on its own (gluon PLAN.md RPN-1).

The capture (`contracts/notification-service/<date>/`, made by its `CAPTURE.sh`
on the laptop) is the port's reference. Each check names the file it found wrong,
relative to the capture, with what it expected and what it found; the scenario
table (`ns_scenarios`) is what `CAPTURE.sh` drove, and what its rows and dead
letters must be.
"""

import json
import shutil
from collections.abc import Callable, Mapping
from dataclasses import asdict
from pathlib import Path

import pytest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue
from opentelemetry.proto.trace.v1.trace_pb2 import Span as ProtoSpan

from gluon_contract.contracts import CONTRACTS_ROOT, latest_capture
from gluon_contract.ns_capture import (
    TIMED_EXCHANGES,
    Problem,
    check_capture,
    check_dead_letters,
    check_exchange,
    check_jsonl,
    check_otlp_export,
    check_sent_email,
    main,
    otlp_to_json,
    write_otlp_json,
)
from gluon_contract.ns_scenarios import (
    DLQ_TOPICS,
    O_CUST,
    SCENARIOS,
    TOPICS,
    U_OK,
    SentEmail,
    event_id,
    expected_dead_letters,
    expected_rows,
)

CAPTURE = latest_capture(CONTRACTS_ROOT, "notification-service")

RESPONSE = (
    b"HTTP/1.1 200 OK\r\n"
    b"Date: Wed, 11 Nov 2026 11:21:32 GMT\r\n"
    b"Connection: keep-alive\r\n"
    b"Content-Length: 0\r\n"
    b"\r\n"
)


def timed(response: bytes, elapsed: str, curl_exit: int) -> bytes:
    """A file as CAPTURE.sh's `timed` writes it: curl -si, then its -w trailer and exit code."""
    return response + f"\n--\nelapsed={elapsed}s\ncurl_exit={curl_exit}\n".encode()


def export(*names: str) -> bytes:
    """An OTLP protobuf export with one span per name, from service `notification-service`."""
    request = ExportTraceServiceRequest()
    resource_spans = request.resource_spans.add()
    resource_spans.resource.attributes.append(
        KeyValue(key="service.name", value=AnyValue(string_value="notification-service"))
    )
    scope_spans = resource_spans.scope_spans.add()
    for index, name in enumerate(names, start=1):
        scope_spans.spans.append(
            ProtoSpan(
                trace_id=bytes.fromhex("4bf92f3577b34da6a3ce929d0e0e4736"),
                span_id=index.to_bytes(8, "big"),
                name=name,
                kind=ProtoSpan.SpanKind.SPAN_KIND_CONSUMER,
                start_time_unix_nano=1794396048475000000,
                attributes=[KeyValue(key="messaging.system", value=AnyValue(string_value="kafka"))],
            )
        )
    return request.SerializeToString()


def row_line(row: SentEmail, **changes: object) -> str:
    """One `db/sent-email.jsonl` line (`row_to_json`) for `row`, with the columns it
    doesn't pin filled in as the capture has them, then `changes` applied."""
    stamp = "2026-11-11T11:20:43.575212+00:00"
    line: dict[str, object] = {
        "id": "9f443147-73e5-488b-9c1d-553acbda1ef2",
        **asdict(row),
        "body": "Welcome.",
        "created_at": stamp,
        "sent_at": stamp if row.status == "sent" else None,
        "failed_at": stamp if row.status == "failed" else None,
    }
    line.update(changes)
    return json.dumps(line, separators=(",", ":"))


def rows_text(*lines: str) -> str:
    """`db/sent-email.jsonl` holding `lines`."""
    return "".join(f"{line}\n" for line in lines)


def all_rows(**changes_by_event: Mapping[str, object]) -> str:
    """Every expected row, changed per source event id."""
    return rows_text(
        *(row_line(row, **changes_by_event.get(row.source_event_id, {})) for row in expected_rows())
    )


def dlq_line(key: str, value: str) -> str:
    """One `kafka-console-consumer.sh` line with timestamp, headers and key printed."""
    return f"CreateTime:1794396048475\tNO_HEADERS\t{key}\t{value}\n"


def short_envelope(event: str, event_type: str = "UserRegistered") -> str:
    """An envelope cut down to what the DLQ check reads (`eventId`); CAPTURE.sh's full
    envelopes are `ns_scenarios.envelope`."""
    return json.dumps(
        {"eventId": event, "eventType": event_type, "payload": {}}, separators=(",", ":")
    )


def names(problems: list[Problem]) -> set[str]:
    """The files the problems name."""
    return {problem.file for problem in problems}


# --- The scenario table -------------------------------------------------------


def test_the_table_has_every_record_capture_sh_publishes() -> None:
    """29 records on the four input topics, in CAPTURE.sh's order."""
    assert len(SCENARIOS) == 29
    assert {scenario.topic for scenario in SCENARIOS} == set(TOPICS)
    assert [s.event_id for s in SCENARIOS[:2]] == [event_id(1), event_id(1)]  # the duplicate


def test_the_table_expects_twenty_rows_one_per_event() -> None:
    """CAPTURE.sh's comments: every email, guest fallback, unresolved and failed lookups."""
    rows = expected_rows()
    assert len(rows) == 20
    assert len({row.source_event_id for row in rows}) == 20
    statuses = [row.status for row in rows]
    assert (statuses.count("sent"), statuses.count("unresolved"), statuses.count("failed")) == (
        16,
        3,
        1,
    )


def test_the_table_expects_five_dead_letters() -> None:
    """user-events `{not json` and event 3, order-events 22 and 50, fulfilment-events 42."""
    dead = {topic: expected_dead_letters(topic) for topic in TOPICS}
    assert [s.raw_value or s.event_id for s in dead["user-events"]] == ["{not json", event_id(3)]
    assert [s.event_id for s in dead["order-events"]] == [event_id(22), event_id(50)]
    assert dead["payment-events"] == ()
    assert [s.event_id for s in dead["fulfilment-events"]] == [event_id(42)]


def test_a_record_that_is_no_envelope_has_a_raw_value_and_no_event() -> None:
    """`{not json` and the null value carry no event id; every other record does."""
    raw = [s for s in SCENARIOS if s.event_id is None]
    assert [(s.topic, s.raw_value) for s in raw] == [
        ("user-events", "{not json"),
        ("user-events", None),
    ]


def test_a_scenario_reads_its_event_type_from_its_envelope() -> None:
    """The first record is the welcome email's UserRegistered; `{not json` has no type."""
    assert SCENARIOS[0].event_type == "UserRegistered"
    assert [s.event_type for s in SCENARIOS if s.raw_value == "{not json"] == [None]


def test_the_tables_values_are_what_capture_sh_published() -> None:
    """Byte for byte: the capture's dead letters are copies of what CAPTURE.sh sent."""
    for topic in TOPICS:
        lines = (CAPTURE / "kafka" / f"{topic}-dlq.txt").read_text(encoding="utf-8").splitlines()
        captured = [tuple(line.split("\t", 3)[2:]) for line in lines]
        assert captured == [(s.key, s.value) for s in expected_dead_letters(topic)], topic


# --- http/*.txt ---------------------------------------------------------------


def test_a_curl_exchange_passes() -> None:
    """A status line, headers, a blank line, a body."""
    assert check_exchange("http/health.txt", RESPONSE) == []


def test_a_file_that_is_no_exchange_fails_naming_it() -> None:
    """What the completion check writes: curl's error, not a response."""
    problems = check_exchange("http/health.txt", b"curl: (7) Failed to connect\n")
    assert names(problems) == {"http/health.txt"}
    assert "not an HTTP response" in problems[0].message


def test_a_timed_file_holds_a_response_and_curls_trailer() -> None:
    """CAPTURE.sh step 9: readiness with Postgres stopped answered, within curl's 20 s."""
    assert "http/health-ready-pg-stopped.txt" in TIMED_EXCHANGES
    raw = timed(RESPONSE.replace(b"200 OK", b"503 Service Unavailable"), "0.008609", 0)
    assert check_exchange("http/health-ready-pg-stopped.txt", raw) == []


def test_a_timed_file_may_hold_only_curls_timeout() -> None:
    """Paused Postgres: no response, curl gave up after 20 s (exit 28)."""
    raw = timed(b"", "20.001943", 28)
    assert check_exchange("http/health-ready-pg-paused.txt", raw) == []


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (timed(b"", "0.01", 7), "curl_exit=7"),
        (timed(b"", "0.01", 0), "not an HTTP response"),
        (RESPONSE, "no curl trailer"),
    ],
    ids=["another-curl-error", "exit-0-without-response", "no-trailer"],
)
def test_a_timed_file_without_a_response_or_timeout_fails(raw: bytes, message: str) -> None:
    """Only curl's timeout excuses a missing response; the trailer is always there."""
    problems = check_exchange("http/health-ready-pg-paused.txt", raw)
    assert names(problems) == {"http/health-ready-pg-paused.txt"}
    assert message in problems[0].message


# --- otlp/*.pb and their .json ------------------------------------------------


def test_an_exports_json_gives_the_same_spans() -> None:
    """The `.json` beside a `.pb` is OTLP/JSON: hex ids, readable, indented."""
    pb = export("user-events process", "GET 127.0.0.1")
    text = otlp_to_json(pb)
    assert '"traceId": "4bf92f3577b34da6a3ce929d0e0e4736"' in text
    assert text.endswith("}\n")
    assert check_otlp_export("otlp/0001.pb", pb, text.encode()) == []


def test_a_json_whose_spans_differ_fails_naming_it() -> None:
    """What the completion check does: another export's `.json` over this one's."""
    problems = check_otlp_export(
        "otlp/0001.pb", export("GET /health/ready"), otlp_to_json(export("a", "b")).encode()
    )
    assert names(problems) == {"otlp/0001.json"}
    assert "GET /health/ready" in problems[0].message


def test_a_missing_json_fails_naming_it() -> None:
    """Every export is decoded beside it."""
    problems = check_otlp_export("otlp/0003.pb", export("x"), None)
    assert names(problems) == {"otlp/0003.json"}


@pytest.mark.parametrize(
    ("pb", "json_body", "file"),
    [
        (b"\xff\xff\xff", None, "otlp/0001.pb"),
        (export("x"), b"{not json", "otlp/0001.json"),
    ],
    ids=["pb", "json"],
)
def test_an_export_that_does_not_decode_fails_naming_it(
    pb: bytes, json_body: bytes | None, file: str
) -> None:
    """Either side unreadable."""
    assert names(check_otlp_export("otlp/0001.pb", pb, json_body)) == {file}


# --- *.jsonl --------------------------------------------------------------------


def test_json_lines_pass() -> None:
    """`requests.jsonl`, `db/*.jsonl`: one JSON value per line."""
    assert check_jsonl("requests.jsonl", '{"a":1}\n{"b":[2]}\n') == []


def test_a_line_that_is_no_json_fails_naming_the_file_and_line() -> None:
    """The line number says where."""
    problems = check_jsonl("db/flyway-history.jsonl", '{"a":1}\n{"b":\n')
    assert names(problems) == {"db/flyway-history.jsonl"}
    assert "line 2" in problems[0].message


# --- kafka/*-dlq.txt --------------------------------------------------------------


def test_the_expected_dead_letters_pass() -> None:
    """Key and event id (or raw value), in the order they were dead-lettered."""
    text = dlq_line(U_OK, "{not json") + dlq_line(U_OK, short_envelope(event_id(3)))
    assert check_dead_letters("kafka/user-events-dlq.txt", "user-events", text) == []


def test_an_empty_dlq_passes_when_none_is_expected() -> None:
    """payment-events dead-letters nothing."""
    assert check_dead_letters("kafka/payment-events-dlq.txt", "payment-events", "") == []


@pytest.mark.parametrize(
    "text",
    [
        dlq_line(U_OK, "{not json"),
        dlq_line(U_OK, short_envelope(event_id(3))) + dlq_line(U_OK, "{not json"),
        dlq_line(O_CUST, "{not json") + dlq_line(U_OK, short_envelope(event_id(3))),
        dlq_line(U_OK, "{not json") + dlq_line(U_OK, short_envelope(event_id(1))),
        dlq_line(U_OK, "{not json") + dlq_line(U_OK, short_envelope(event_id(3))) + "garbage\n",
    ],
    ids=["missing", "reordered", "other-key", "other-event", "unparsable-line"],
)
def test_other_dead_letters_fail_naming_the_file(text: str) -> None:
    """Exactly the table's dead letters, nothing else."""
    problems = check_dead_letters("kafka/user-events-dlq.txt", "user-events", text)
    assert names(problems) == {"kafka/user-events-dlq.txt"}


# --- db/sent-email.jsonl --------------------------------------------------------------


def test_the_expected_rows_pass() -> None:
    """Every row of the table, whatever their order, ids, bodies and times."""
    lines = [row_line(row) for row in expected_rows()]
    assert check_sent_email("db/sent-email.jsonl", rows_text(*reversed(lines))) == []


def test_a_row_with_another_status_fails_naming_the_file_and_event() -> None:
    """What the completion check does: the first `sent` row made `pending`."""
    first = event_id(1)
    problems = check_sent_email(
        "db/sent-email.jsonl", all_rows(**{first: {"status": "pending", "sent_at": None}})
    )
    assert names(problems) == {"db/sent-email.jsonl"}
    assert first in problems[0].message
    assert "'sent'" in problems[0].message
    assert "'pending'" in problems[0].message


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"recipient_email": "other@example.com"}, "recipient_email"),
        ({"sent_at": None}, "sent_at"),
        ({"failed_at": "2026-11-11T11:21:36.144438+00:00"}, "failed_at"),
    ],
    ids=["column", "sent-without-sent-at", "sent-with-failed-at"],
)
def test_a_changed_row_fails(changes: dict[str, object], message: str) -> None:
    """Every column but id, body and the timestamps; those as the status says."""
    problems = check_sent_email("db/sent-email.jsonl", all_rows(**{event_id(10): changes}))
    assert names(problems) == {"db/sent-email.jsonl"}
    assert message in problems[0].message


def test_a_missing_row_fails() -> None:
    """Event 50's failed row is part of the table."""
    lines = [row_line(row) for row in expected_rows() if row.source_event_id != event_id(50)]
    problems = check_sent_email("db/sent-email.jsonl", rows_text(*lines))
    assert [event_id(50) in problem.message for problem in problems] == [True]


def test_an_extra_or_duplicate_row_fails() -> None:
    """Event 1 twice (the duplicate must not make a row), and an event never sent."""
    extra = row_line(expected_rows()[0], source_event_id=event_id(99))
    again = row_line(expected_rows()[0], id="01270a34-e72f-462f-bd17-d3545b8d90f1")
    problems = check_sent_email("db/sent-email.jsonl", all_rows() + rows_text(extra, again))
    assert [problem.message for problem in problems] == [
        f"line 21: a row for event {event_id(99)}, not in the scenario table",
        f"line 22: a second row for event {event_id(1)}",
    ]


def test_a_row_that_is_not_json_fails() -> None:
    """Reported as such, not as a missing row only."""
    problems = check_sent_email("db/sent-email.jsonl", all_rows() + "{\n")
    assert names(problems) == {"db/sent-email.jsonl"}


# --- A capture directory ----------------------------------------------------------------


@pytest.fixture
def capture_copy(tmp_path: Path) -> Path:
    """A copy of the committed capture, its OTLP exports decoded beside them."""
    copy = tmp_path / "capture"
    shutil.copytree(CAPTURE, copy)
    write_otlp_json(copy)
    return copy


def test_decoding_writes_one_json_per_export(capture_copy: Path) -> None:
    """`decode-otlp`: each `.pb`'s `.json`, the same spans; running it again changes nothing."""
    pbs = sorted((capture_copy / "otlp").glob("*.pb"))
    jsons = sorted((capture_copy / "otlp").glob("*.json"))
    assert [p.stem for p in pbs] == [j.stem for j in jsons]
    before = {j.name: j.read_bytes() for j in jsons}
    write_otlp_json(capture_copy)
    assert {j.name: j.read_bytes() for j in jsons} == before


def test_a_copy_of_the_capture_passes(capture_copy: Path) -> None:
    """Every file the check reads, no problem found."""
    results = check_capture(capture_copy)
    assert [problem for result in results for problem in result.problems] == []
    checked = {result.file for result in results}
    assert {"http/health.txt", "otlp/0001.pb", "db/sent-email.jsonl"} <= checked
    assert {f"kafka/{topic}.txt" for topic in DLQ_TOPICS} <= checked


def first_sent_made_pending(capture: Path) -> None:
    """What bin/verify-complete-RPN-1.sh does to a copy: the first `sent` row made `pending`."""
    rows = capture / "db" / "sent-email.jsonl"
    text = rows.read_text(encoding="utf-8")
    rows.write_text(text.replace('"status":"sent"', '"status":"pending"', 1), encoding="utf-8")


@pytest.mark.parametrize(
    ("file", "break_copy"),
    [
        (
            "http/health.txt",
            lambda c: (c / "http" / "health.txt").write_bytes(b"curl: (7) Failed to connect\n"),
        ),
        (
            "otlp/0001.json",
            lambda c: shutil.copy(c / "otlp" / "0002.json", c / "otlp" / "0001.json"),
        ),
        ("db/sent-email.jsonl", first_sent_made_pending),
        (
            "kafka/order-events-dlq.txt",
            lambda c: (c / "kafka" / "order-events-dlq.txt").write_bytes(b""),
        ),
        ("requests.jsonl", lambda c: (c / "requests.jsonl").write_bytes(b"{\n")),
    ],
    ids=["http", "otlp", "row", "dlq", "jsonl"],
)
def test_main_fails_naming_the_broken_file(
    capture_copy: Path,
    file: str,
    break_copy: Callable[[Path], object],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`check DIR`: FAIL naming the file relative to the capture, exit 1."""
    break_copy(capture_copy)
    assert main(["check", str(capture_copy)]) == 1
    out = capsys.readouterr().out
    assert f"FAIL {file}" in out
    assert out.rstrip().splitlines()[-1].startswith("FAIL")


def test_main_passes_a_good_copy(capture_copy: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`check DIR`: an ok line per file, then PASS, exit 0."""
    assert main(["check", str(capture_copy)]) == 0
    out = capsys.readouterr().out
    assert "ok   db/sent-email.jsonl" in out
    assert out.rstrip().splitlines()[-1].startswith("PASS")


def test_main_decodes_the_exports(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`decode-otlp DIR` writes the `.json` files."""
    copy = tmp_path / "capture"
    shutil.copytree(CAPTURE, copy)
    assert main(["decode-otlp", str(copy)]) == 0
    assert (copy / "otlp" / "0014.json").is_file()
    assert "0014.json" in capsys.readouterr().out


def test_a_json_without_its_export_fails_naming_it(
    capture_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `.json` whose `.pb` is gone can't be checked against it."""
    shutil.copy(capture_copy / "otlp" / "0001.json", capture_copy / "otlp" / "0099.json")
    assert main(["check", str(capture_copy)]) == 1
    assert "FAIL otlp/0099.json: no .pb export beside it" in capsys.readouterr().out


@pytest.mark.parametrize("file", ["kafka/payment-events-dlq.txt", "db/sent-email.jsonl"])
def test_a_missing_dlq_or_rows_file_raises(capture_copy: Path, file: str) -> None:
    """Even payment-events' empty DLQ dump must be there; as user-service's `capture_file`,
    a missing file is a FileNotFoundError naming it."""
    (capture_copy / file).unlink()
    with pytest.raises(FileNotFoundError, match=file):
        check_capture(capture_copy)


@pytest.mark.parametrize("command", ["check", "decode-otlp"])
def test_a_path_that_is_no_directory_fails(
    tmp_path: Path, command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """A mistyped capture path says so."""
    missing = tmp_path / "no-such-capture"
    assert main([command, str(missing)]) == 1
    assert capsys.readouterr().out == f"FAIL: {missing} is not a directory\n"


def test_the_committed_capture_passes() -> None:
    """The latest notification-service capture, as committed, with its decoded exports."""
    results = check_capture(CAPTURE)
    assert [problem for result in results for problem in result.problems] == []
