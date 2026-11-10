# SPDX-License-Identifier: MIT

"""Cluster mode's settings and the console-consumer topic reader (RUST-5.4, prepared)."""

import shlex
import sys
from pathlib import Path

import pytest

from gluon_contract.cdc import CdcError
from gluon_contract.cluster import (
    DEFAULT_CONSOLE_CONSUMER,
    ConsoleTopicReader,
    cluster_settings,
    parse_console_line,
)


def test_no_base_url_means_isolated_mode() -> None:
    """Nothing set: None (isolated mode)."""
    assert cluster_settings({}) is None


def test_a_base_url_switches_to_cluster_mode_with_gluon_locals_consumer() -> None:
    """The URL without a trailing slash; the default consumer runs in gluon-local's Kafka pod."""
    settings = cluster_settings({"CONTRACT_BASE_URL": "http://user-service.gluon-local:8080/"})
    assert settings is not None
    assert settings.base_url == "http://user-service.gluon-local:8080"
    assert settings.console_consumer == DEFAULT_CONSOLE_CONSUMER
    assert DEFAULT_CONSOLE_CONSUMER[:3] == ("kubectl", "exec", "-n")
    assert "kafka-console-consumer.sh" in " ".join(DEFAULT_CONSOLE_CONSUMER)


def test_the_console_consumer_command_can_be_replaced() -> None:
    """CONTRACT_KAFKA_CONSOLE_CONSUMER, split like a shell command."""
    settings = cluster_settings(
        {
            "CONTRACT_BASE_URL": "http://x",
            "CONTRACT_KAFKA_CONSOLE_CONSUMER": "java -cp 'a b/*' Main",
        }
    )
    assert settings is not None
    assert settings.console_consumer == ("java", "-cp", "a b/*", "Main")


def test_a_console_line_is_headers_key_and_value() -> None:
    """print.headers and print.key: 'h1:v1,h2:v2<TAB>key<TAB>value'; NULL: a value-less header."""
    record = parse_console_line(
        "user-events",
        'id:7921,traceparent:00-0af7-01,correlation_id:51ac\t51ac\t{"a": 1, "b": "x\ty"}',
    )
    assert record.key == "51ac"
    assert record.value == '{"a": 1, "b": "x\ty"}'
    assert record.headers == {"id": "7921", "traceparent": "00-0af7-01", "correlation_id": "51ac"}
    bare = parse_console_line("t", "NO_HEADERS\tk\tv")
    assert bare.headers == {}
    nulls = parse_console_line("t", "traceparent:NULL\tk\tv")
    assert nulls.headers == {"traceparent": None}


def fake_consumer(tmp_path: Path, lines: list[str]) -> tuple[str, ...]:
    """A stand-in console consumer printing `lines`."""
    script = tmp_path / "consumer.py"
    script.write_text(f"import sys\nfor line in {lines!r}:\n    print(line)\n")
    return (sys.executable, str(script))


def test_the_reader_returns_the_first_matching_record(tmp_path: Path) -> None:
    """It runs the command with the topic and from-beginning arguments and parses each line."""
    reader = ConsoleTopicReader(
        fake_consumer(tmp_path, ["NO_HEADERS\ta\t1", "correlation_id:b\tb\t2"])
    )
    record = reader.record("user-events", lambda r: r.key == "b", timeout_s=10)
    assert (record.key, record.value, record.headers) == ("b", "2", {"correlation_id": "b"})


def test_the_reader_says_what_it_saw_when_nothing_matches(tmp_path: Path) -> None:
    """A CdcError listing the last records read."""
    reader = ConsoleTopicReader(fake_consumer(tmp_path, ["NO_HEADERS\ta\t1"]))
    with pytest.raises(CdcError, match="no matching record on user-events"):
        reader.record("user-events", lambda r: r.key == "z", timeout_s=2)
    assert shlex.join(reader.argv("user-events", 1000))
