# SPDX-License-Identifier: MIT

"""The throwaway Kafka broker (RUST-6.1): produce, read, an outage, committed offsets.

Needs the jars `bin/sandbox-setup --only cdc` installs; skipped, visibly, without them.
"""

import os
import socket
import time
from pathlib import Path

import pytest
from kafka import KafkaAdminClient, KafkaConsumer

from gluon_contract.cdc import cdc_home
from gluon_contract.kafka import KafkaBroker
from gluon_contract.supervisor import StackError

HOME = cdc_home(os.environ)
pytestmark = pytest.mark.skipif(
    not (HOME / "COMPLETE").is_file(),
    reason=f"no CDC jars in {HOME} (bin/sandbox-setup --only cdc)",
)


def test_what_is_produced_is_read_back_with_key_and_headers(tmp_path: Path) -> None:
    """A record with a key and headers round-trips."""
    with KafkaBroker(HOME, tmp_path) as kafka:
        kafka.produce("user-events", "k1", "v1", {"traceparent": "tp"})
        record = kafka.record("user-events", lambda r: r.key == "k1", timeout_s=30)
    assert (record.value, record.headers) == ("v1", {"traceparent": "tp"})


def test_an_outage_stops_the_broker_and_a_restart_keeps_its_port_and_data(tmp_path: Path) -> None:
    """After stop() nothing listens; after start() the earlier record is still there."""
    with KafkaBroker(HOME, tmp_path) as kafka:
        kafka.produce("user-events", "before", "v", {})
        kafka.stop()
        with socket.socket() as probe:
            assert probe.connect_ex(("127.0.0.1", kafka.port)) != 0
        kafka.start()
        record = kafka.record("user-events", lambda r: r.key == "before", timeout_s=60)
    assert record.value == "v"


def test_produce_returns_each_records_offset(tmp_path: Path) -> None:
    """The offset the broker gave the record, a null value's included (RPN-10: a check
    waits for the consumer to commit past its own record)."""
    with KafkaBroker(HOME, tmp_path) as kafka:
        offsets = [
            kafka.produce("user-events", "a", "1", {}),
            kafka.produce("user-events", "b", None, {}),
            kafka.produce("user-events", None, "3", {"traceparent": "tp"}),
        ]
    assert offsets == [0, 1, 2]


def test_a_group_is_there_once_a_consumer_has_joined_even_without_a_commit(
    tmp_path: Path,
) -> None:
    """No group before any consumer joins; there once one has, committed or not, and
    still there after it leaves (RPN-10: "not yet implemented" means no consumer ever
    joined)."""
    with KafkaBroker(HOME, tmp_path) as kafka:
        kafka.create_topics(["user-events"])
        before = kafka.has_group("joiner")
        consumer = KafkaConsumer(
            "user-events",
            bootstrap_servers=kafka.bootstrap,
            group_id="joiner",
            auto_offset_reset="earliest",
            enable_auto_commit=False,
            consumer_timeout_ms=3000,
        )
        list(consumer)
        joined = kafka.has_group("joiner")
        consumer.close()
        left = kafka.has_group("joiner")
        other = kafka.has_group("someone-else")
    assert (before, joined, left, other) == (False, True, True, False)


def test_records_now_reads_to_the_end_without_waiting_to_settle(tmp_path: Path) -> None:
    """Every record up to the topic's end offset when asked, in order, a null value and
    headers included; at once, not after a settle period (RPN-10 review M3); a topic
    nobody has written to has none."""
    with KafkaBroker(HOME, tmp_path) as kafka:
        kafka.produce("user-events-dlq", "a", "1", {})
        kafka.produce("user-events-dlq", "b", None, {"h": "v"})
        started = time.monotonic()
        found = kafka.records_now("user-events-dlq")
        elapsed = time.monotonic() - started
        empty = kafka.records_now("order-events-dlq")
    assert [(r.key, r.value, r.headers) for r in found] == [
        ("a", "1", {}),
        ("b", None, {"h": "v"}),
    ]
    assert elapsed < 2, elapsed
    assert empty == []


def test_committed_offsets_are_read_per_group(tmp_path: Path) -> None:
    """What a consumer group committed, by partition."""
    with KafkaBroker(HOME, tmp_path) as kafka:
        kafka.produce("user-events", "a", "1", {})
        kafka.produce("user-events", "b", "2", {})
        assert kafka.committed("probe-group", "user-events") == {}
        consumer = KafkaConsumer(
            "user-events",
            bootstrap_servers=kafka.bootstrap,
            group_id="probe-group",
            auto_offset_reset="earliest",
            enable_auto_commit=False,
            consumer_timeout_ms=5000,
        )
        seen = [message.key for message in consumer]
        consumer.commit()
        consumer.close()
        assert seen == [b"a", b"b"]
        assert kafka.committed("probe-group", "user-events") == {0: 2}


def test_topics_are_created_and_creating_them_again_is_harmless(tmp_path: Path) -> None:
    """Absent before create_topics, there after it (listing them creates nothing); a second
    call with the same topics changes nothing and raises nothing."""
    wanted = {"order-events", "payment-events"}
    with KafkaBroker(HOME, tmp_path) as kafka:
        before = topics_on(kafka)
        kafka.create_topics(sorted(wanted))
        after = topics_on(kafka)
        kafka.create_topics(sorted(wanted))
        again = topics_on(kafka)
    assert before & wanted == set()
    assert after & wanted == wanted
    assert again == after


def test_creating_topics_on_a_broker_that_isnt_there_gives_up_at_its_deadline(
    tmp_path: Path,
) -> None:
    """Retried while the broker doesn't answer, then a StackError naming the topics, near
    the deadline rather than after the client's own 30 s bootstrap timeout."""
    with KafkaBroker(HOME, tmp_path) as kafka:
        kafka.stop()
        started = time.monotonic()
        with pytest.raises(StackError, match="order-events, payment-events"):
            kafka.create_topics(["order-events", "payment-events"], timeout_s=3)
        elapsed = time.monotonic() - started
    assert 3 <= elapsed < 10, elapsed


def topics_on(kafka: KafkaBroker) -> set[str]:
    """The broker's topics now, from its metadata."""
    admin = KafkaAdminClient(bootstrap_servers=kafka.bootstrap)
    try:
        return set(admin.list_topics())
    finally:
        admin.close()
