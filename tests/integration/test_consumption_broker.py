# SPDX-License-Identifier: MIT

"""A replay against a real broker (gluon RPN-10): no consumer is "not yet implemented",
a consumer that never commits is "not consumed", one that commits gets there.

Needs the jars `bin/sandbox-setup --only cdc` installs; skipped, visibly, without them.
"""

import os
from pathlib import Path

import pytest
from kafka import KafkaConsumer

from gluon_contract.cdc import cdc_home
from gluon_contract.consumption import replay
from gluon_contract.kafka import KafkaBroker
from gluon_contract.notification_scenarios import scenarios
from gluon_contract.pending import NOT_YET_IMPLEMENTED

HOME = cdc_home(os.environ)
pytestmark = pytest.mark.skipif(
    not (HOME / "COMPLETE").is_file(),
    reason=f"no CDC jars in {HOME} (bin/sandbox-setup --only cdc)",
)
TOPIC = "user-events"


def consume_all(kafka: KafkaBroker, group: str, *, commit: bool) -> int:
    """Joins `group`, reads the topic to its end, commits if asked; how many it read."""
    consumer = KafkaConsumer(
        TOPIC,
        bootstrap_servers=kafka.bootstrap,
        group_id=group,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        consumer_timeout_ms=5000,
    )
    try:
        read = sum(1 for _ in consumer)
        if commit:
            consumer.commit()
        return read
    finally:
        consumer.close()


def test_a_replay_tells_absent_stuck_and_done_apart(tmp_path: Path) -> None:
    """The user-events records replayed for each of three groups on one broker."""
    with KafkaBroker(HOME, tmp_path) as kafka:
        kafka.create_topics([TOPIC])
        records = scenarios(TOPIC)

        absent = replay(kafka, TOPIC, "nobody", records, within_s=2)
        with pytest.raises(AssertionError, match=NOT_YET_IMPLEMENTED):
            absent.consumed(0)

        stuck = replay(kafka, TOPIC, "stuck", records, within_s=2)
        consume_all(kafka, "stuck", commit=False)
        with pytest.raises(AssertionError, match="not consumed by stuck") as raised:
            stuck.consumed(0)
        assert NOT_YET_IMPLEMENTED not in str(raised.value)

        done = replay(kafka, TOPIC, "done", records, within_s=20)
        consume_all(kafka, "done", commit=True)
        last = done.consumed(len(records) - 1)
        assert last.offset == done.records[-1].offset == 3 * len(records) - 1
