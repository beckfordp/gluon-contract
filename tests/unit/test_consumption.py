# SPDX-License-Identifier: MIT

"""Replaying a topic's captured records and waiting for a consumer group (gluon RPN-10).

A fake broker and clock: nothing waits, nothing is started.
"""

from collections.abc import Mapping

import pytest
from kafka.errors import CoordinatorNotAvailableError

from gluon_contract.consumption import Replay, replay
from gluon_contract.notification_scenarios import TRACEPARENT, Scenario, scenarios
from gluon_contract.pending import NOT_YET_IMPLEMENTED

TOPIC = "user-events"
GROUP = "notification-service-user-events"


class FakeBroker:
    """Takes records, and answers for a group as scripted: joined or not, and the offsets
    committed on each successive poll (the last one repeats)."""

    def __init__(
        self, *, joined: bool = True, commits: list[int | Exception] | None = None
    ) -> None:
        self.sent: list[tuple[str, str | None, str | None, dict[str, str]]] = []
        self.joined = joined
        self.commits = list(commits or [])
        self.polls = 0

    def produce(
        self, topic: str, key: str | None, value: str | None, headers: Mapping[str, str]
    ) -> int:
        self.sent.append((topic, key, value, dict(headers)))
        return len(self.sent) - 1

    def has_group(self, group: str) -> bool:
        return self.joined and group == GROUP

    def committed(self, group: str, topic: str, *, timeout_s: float = 30.0) -> dict[int, int]:
        self.polls += 1
        if not self.commits:
            return {}
        answer = self.commits.pop(0) if len(self.commits) > 1 else self.commits[0]
        if isinstance(answer, Exception):
            raise answer
        return {0: answer}


class FakeClock:
    """Time moves only when the code under test sleeps."""

    def __init__(self) -> None:
        self.now = 100.0
        self.slept = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds
        self.slept += seconds


def replayed(broker: FakeBroker, clock: FakeClock, within_s: float = 30.0) -> Replay:
    """The user-events records replayed on the fake broker, timed by the fake clock."""
    return replay(
        broker, TOPIC, GROUP, scenarios(TOPIC), within_s=within_s, clock=clock, sleep=clock.sleep
    )


def test_the_records_are_published_in_order_as_captured() -> None:
    """Key, value (the null one included) and the traceparent header where CAPTURE.sh sent
    one; each record's offset kept."""
    broker, clock = FakeBroker(), FakeClock()
    replay_ = replayed(broker, clock)
    expected: list[Scenario] = list(scenarios(TOPIC))
    assert broker.sent == [
        (TOPIC, s.key, s.value, {"traceparent": TRACEPARENT} if s.traceparent else {})
        for s in expected
    ]
    assert [r.offset for r in replay_.records] == list(range(6))
    assert [r.scenario for r in replay_.records] == expected


def test_a_record_already_committed_past_is_consumed_at_once() -> None:
    """The committed offset is the next to read, so offset 3 is done once it is 4."""
    broker, clock = FakeBroker(commits=[4]), FakeClock()
    record = replayed(broker, clock).consumed(3)
    assert (record.offset, clock.slept) == (3, 0.0)


def test_it_polls_until_the_group_commits_past_the_record() -> None:
    """Nothing, then short of it, then past it."""
    broker, clock = FakeBroker(commits=[0, 1, 2]), FakeClock()
    replayed(broker, clock).consumed(1)
    assert broker.polls == 3
    assert 0 < clock.slept < 30


def test_no_consumer_ever_joining_is_not_yet_implemented() -> None:
    """PENDING: at the deadline, no group at all: the record and the group named."""
    broker, clock = FakeBroker(joined=False), FakeClock()
    with pytest.raises(AssertionError) as raised:
        replayed(broker, clock).consumed(2)
    message = str(raised.value)
    assert NOT_YET_IMPLEMENTED in message
    assert "user-events record 2 (unrelated type)" in message
    assert GROUP in message
    assert clock.slept == pytest.approx(30, abs=0.5)


def test_a_group_that_joined_but_never_got_there_is_not_consumed() -> None:
    """FAIL, not PENDING: the consumer exists; the record wasn't committed in time."""
    broker, clock = FakeBroker(joined=True, commits=[2]), FakeClock()
    with pytest.raises(AssertionError) as raised:
        replayed(broker, clock).consumed(4)
    message = str(raised.value)
    assert NOT_YET_IMPLEMENTED not in message
    assert "user-events record 4 (undecodable payload) not consumed" in message
    assert f"by {GROUP} within 30" in message
    assert "committed offset 2" in message


def test_kafka_errors_while_waiting_are_not_yet() -> None:
    """A coordinator still loading is no answer: keep polling."""
    error = CoordinatorNotAvailableError()
    broker, clock = FakeBroker(commits=[error, error, 6]), FakeClock()
    assert replayed(broker, clock).consumed(5).offset == 5


def test_the_deadline_is_shared_by_every_wait() -> None:
    """One deadline for the replay: once it has passed, the next wait fails at once rather
    than waiting its own 30 s (six pending checks cost one deadline, not six)."""
    broker, clock = FakeBroker(joined=False), FakeClock()
    replay_ = replayed(broker, clock, within_s=10)
    with pytest.raises(AssertionError):
        replay_.consumed(0)
    slept = clock.slept
    with pytest.raises(AssertionError, match=NOT_YET_IMPLEMENTED):
        replay_.consumed(1)
    assert clock.slept == slept


def test_an_index_outside_the_replay_is_an_error() -> None:
    """A check asking for a record that wasn't replayed is the check's mistake."""
    with pytest.raises(IndexError):
        replayed(FakeBroker(commits=[6]), FakeClock()).consumed(6)


def test_a_group_kafka_wont_describe_is_not_taken_for_absent() -> None:
    """No answer about the group is no evidence the feature is missing: "not consumed"
    (FAIL), never NOT_YET_IMPLEMENTED."""

    class Silent(FakeBroker):
        def has_group(self, group: str) -> bool:
            raise CoordinatorNotAvailableError()

    broker, clock = Silent(joined=False), FakeClock()
    with pytest.raises(AssertionError) as raised:
        replayed(broker, clock).consumed(0)
    assert "not consumed" in str(raised.value)
    assert NOT_YET_IMPLEMENTED not in str(raised.value)
