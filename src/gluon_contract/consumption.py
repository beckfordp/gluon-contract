# SPDX-License-Identifier: MIT

"""Replaying a topic's captured records to the service under test, and waiting for its
consumer group to get through them (gluon RPN-10).

A consumer check publishes the records its capture published (`notification_scenarios`),
then, for the record it judges, waits until the service's consumer group has committed
past it: the Scala consumers commit a record's offset only after handling it, so from
then on its outcome (a row, a dead letter, nothing) is there to look at, and a check
that expects nothing can't pass just because nothing happened yet.

One deadline serves every wait of a replay, so a group whose consumer doesn't exist
costs one deadline, not one per check. At the deadline the wait fails, saying:
  - NOT_YET_IMPLEMENTED (`gluon_contract.pending`) if no consumer ever joined the group:
    the feature isn't built; the check is PENDING;
  - "not consumed" if the group exists but hasn't committed past the record: a FAIL.
Kafka errors while polling (a coordinator still loading) are "not yet".

The input topics have one partition (CAPTURE.sh creates them so, as the harness does),
so a record's offset is on partition 0.
"""

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from kafka.errors import KafkaError

from gluon_contract.notification_scenarios import Scenario
from gluon_contract.pending import NOT_YET_IMPLEMENTED

POLL_S = 0.2
"""How often a wait asks for the group's committed offset."""


class Broker(Protocol):
    """What a replay needs of the broker (`gluon_contract.kafka.KafkaBroker`)."""

    def produce(
        self, topic: str, key: str | None, value: str | None, headers: Mapping[str, str]
    ) -> int:
        """Sends one record; its offset."""
        ...

    def has_group(self, group: str) -> bool:
        """Whether a consumer has ever joined `group`."""
        ...

    def committed(self, group: str, topic: str, *, timeout_s: float = 30.0) -> dict[int, int]:
        """`group`'s committed offsets on `topic`, by partition."""
        ...


@dataclass(frozen=True, slots=True)
class Replayed:
    """One published record: the scenario it came from and the offset it got."""

    scenario: Scenario
    offset: int


class Replay:
    """A topic's records, published; `consumed` waits for the group to get past one."""

    def __init__(
        self,
        broker: Broker,
        topic: str,
        group: str,
        records: Sequence[Replayed],
        *,
        within_s: float,
        clock: Callable[[], float],
        sleep: Callable[[float], None],
    ) -> None:
        self.topic = topic
        self.group = group
        self.records = list(records)
        self.within_s = within_s
        self.deadline = clock() + within_s
        self._broker = broker
        self._clock = clock
        self._sleep = sleep

    def consumed(self, index: int) -> Replayed:
        """Waits until the group has committed past the `index`th record; returns it.

        Raises:
            IndexError: no such record in the replay.
            AssertionError: not by the replay's deadline, saying NOT_YET_IMPLEMENTED if
                no consumer ever joined the group, else "not consumed".
        """
        record = self.records[index]
        committed: int | None = None
        while True:
            committed = self._committed(committed)
            if committed is not None and committed > record.offset:
                return record
            if self._clock() >= self.deadline:
                raise AssertionError(self._why_not(record, committed))
            self._sleep(min(POLL_S, max(0.0, self.deadline - self._clock())))

    def _committed(self, last: int | None) -> int | None:
        """The group's committed offset now; the last one seen if Kafka doesn't answer."""
        try:
            return self._broker.committed(self.group, self.topic).get(0, last)
        except KafkaError:
            return last

    def _why_not(self, record: Replayed, committed: int | None) -> str:
        what = f"{self.topic} record {record.offset} ({record.scenario.comment})"
        try:
            joined = self._broker.has_group(self.group)
        except KafkaError:
            joined = True  # unknown: not evidence that the feature is absent
        if not joined:
            return (
                f"{what}: {NOT_YET_IMPLEMENTED}: no consumer ever joined group "
                f"{self.group} within {self.within_s:g}s"
            )
        at = "no committed offset" if committed is None else f"committed offset {committed}"
        return f"{what} not consumed by {self.group} within {self.within_s:g}s ({at})"


def replay(
    broker: Broker,
    topic: str,
    group: str,
    scenarios: Sequence[Scenario],
    *,
    within_s: float = 30.0,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> Replay:
    """Publishes `scenarios` to `topic` in order, as captured (key, value, the traceparent
    header where there was one); `group` is the consumer group to wait for, and the
    replay's one deadline is `within_s` from when the last record is published."""
    records = [
        Replayed(
            scenario,
            broker.produce(
                topic,
                scenario.key,
                scenario.value,
                {} if scenario.traceparent is None else {"traceparent": scenario.traceparent},
            ),
        )
        for scenario in scenarios
    ]
    return Replay(broker, topic, group, records, within_s=within_s, clock=clock, sleep=sleep)
