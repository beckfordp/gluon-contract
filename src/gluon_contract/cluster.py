# SPDX-License-Identifier: MIT

"""Cluster mode (gluon PLAN.md RUST-5.4): the checks marked `cluster`, run against a
deployment that is already running (gluon-local), starting nothing.

`CONTRACT_BASE_URL` switches it on. The real `user-events` topic is read through
Kafka's console consumer, by default inside gluon-local's Kafka pod (its advertised
listener, `kafka:9092`, only resolves inside the cluster);
`CONTRACT_KAFKA_CONSOLE_CONSUMER` replaces the command.
"""

import shlex
import subprocess
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from gluon_contract.cdc import CdcError, Record

DEFAULT_CONSOLE_CONSUMER = (
    "kubectl",
    "exec",
    "-n",
    "gluon-local",
    "deploy/kafka",
    "--",
    "/opt/kafka/bin/kafka-console-consumer.sh",
    "--bootstrap-server",
    "localhost:9092",
)


@dataclass(frozen=True, slots=True)
class ClusterSettings:
    """Where the deployed service answers, and how to read its topic."""

    base_url: str
    console_consumer: tuple[str, ...]


def cluster_settings(raw: Mapping[str, str]) -> ClusterSettings | None:
    """Cluster mode's settings from `CONTRACT_*` values, or None (isolated mode)."""
    base_url = (raw.get("CONTRACT_BASE_URL") or "").strip()
    if not base_url:
        return None
    command = raw.get("CONTRACT_KAFKA_CONSOLE_CONSUMER")
    return ClusterSettings(
        base_url=base_url.rstrip("/"),
        console_consumer=tuple(shlex.split(command)) if command else DEFAULT_CONSOLE_CONSUMER,
    )


@dataclass(frozen=True, slots=True)
class ClusterHarness:
    """What cluster-mode checks get as `harness`: the deployment's base URL."""

    base_url: str


def parse_console_line(topic: str, line: str) -> Record:
    """One `print.headers`/`print.key` line: `h:v,h:v<TAB>key<TAB>value` (`NO_HEADERS`
    when there are none, `NULL` for a header written with no value)."""
    headers_text, key, value = line.split("\t", 2)
    headers: dict[str, str | None] = {}
    if headers_text != "NO_HEADERS":
        for pair in headers_text.split(","):
            name, _, text = pair.partition(":")
            headers[name] = None if text == "NULL" else text
    return Record(topic=topic, key=None if key == "null" else key, value=value, headers=headers)


class ConsoleTopicReader:
    """Reads a topic from the beginning with a console consumer command."""

    def __init__(self, command: tuple[str, ...]) -> None:
        self.command = command

    def argv(self, topic: str, timeout_ms: int) -> list[str]:
        """The full command line for `topic`."""
        return [
            *self.command,
            "--topic",
            topic,
            "--from-beginning",
            "--timeout-ms",
            str(timeout_ms),
            "--property",
            "print.key=true",
            "--property",
            "print.headers=true",
        ]

    def record(
        self, topic: str, until: Callable[[Record], bool], *, timeout_s: float = 60.0
    ) -> Record:
        """The first record on `topic` that `until` accepts.

        Raises:
            CdcError: none within `timeout_s`, listing the last records seen.
        """
        seen: list[Record] = []
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            remaining_ms = max(1000, int((deadline - time.monotonic()) * 1000))
            process = subprocess.Popen(
                self.argv(topic, remaining_ms),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            try:
                assert process.stdout is not None
                for line in process.stdout:
                    if line.count("\t") < 2:
                        continue
                    record = parse_console_line(topic, line.rstrip("\n"))
                    if until(record):
                        return record
                    seen.append(record)
            finally:
                process.kill()
                process.wait()
            seen = seen[-5:]
            time.sleep(0.5)
        raise CdcError(f"no matching record on {topic} after {timeout_s}s; saw {seen}")
