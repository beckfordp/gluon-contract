# SPDX-License-Identifier: MIT

"""The throwaway Kafka broker (RUST-6.1): produce, read, an outage, committed offsets.

Needs the jars `bin/sandbox-setup --only cdc` installs; skipped, visibly, without them.
"""

import os
import socket
from pathlib import Path

import pytest
from kafka import KafkaConsumer

from gluon_contract.cdc import KafkaBroker, cdc_home

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
