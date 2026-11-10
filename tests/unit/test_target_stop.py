# SPDX-License-Identifier: MIT

"""Stopping the target waits until its process group is really empty."""

import os

import pytest

from gluon_contract.target import TargetError, group_alive, only_zombies, wait_for_group_exit


class FakeClock:
    """A clock that only moves when the code under test sleeps."""

    def __init__(self) -> None:
        """Starts at zero."""
        self.now = 0.0
        self.sleeps = 0

    def monotonic(self) -> float:
        """The current fake time."""
        return self.now

    def sleep(self, seconds: float) -> None:
        """Advances the fake time."""
        self.now += seconds
        self.sleeps += 1


def test_it_returns_once_the_last_member_has_gone() -> None:
    """Members still dying after SIGKILL are waited for, not raced."""
    answers = iter([True, True, False])
    clock = FakeClock()
    wait_for_group_exit(
        4242, 5.0, alive=lambda _group: next(answers), sleep=clock.sleep, clock=clock.monotonic
    )
    assert clock.sleeps == 2


def test_an_empty_group_needs_no_wait() -> None:
    """A group with nothing left returns at once."""
    clock = FakeClock()
    wait_for_group_exit(
        4242, 5.0, alive=lambda _group: False, sleep=clock.sleep, clock=clock.monotonic
    )
    assert clock.sleeps == 0


def test_a_member_outliving_the_deadline_is_a_target_error() -> None:
    """stop() never returns with a member running: past the deadline it says so."""
    clock = FakeClock()
    with pytest.raises(TargetError, match=r"process group 4242 .*ps -A -o pid=,pgid=,command="):
        wait_for_group_exit(
            4242,
            1.0,
            alive=lambda _group: True,
            stopped=lambda _group: False,
            sleep=clock.sleep,
            clock=clock.monotonic,
        )
    assert clock.now >= 1.0


def test_members_left_only_as_zombies_pass_at_the_deadline() -> None:
    """A zombie nobody reaps (a container's PID 1) has stopped: no error."""
    clock = FakeClock()
    wait_for_group_exit(
        4242,
        1.0,
        alive=lambda _group: True,
        stopped=lambda _group: True,
        sleep=clock.sleep,
        clock=clock.monotonic,
    )
    assert clock.now >= 1.0


@pytest.mark.parametrize(
    ("listing", "expected"),
    [
        ("", True),
        ("    1 Ss\n 4242 Z\n 4242 Z+\n", True),
        (" 4242 Z\n 4242 S\n", False),
        (" 4242 R+\n", False),
        (" 42421 S\n  424 R\n 4242 Z\n", True),
    ],
)
def test_only_zombies_reads_the_states_of_the_groups_members(listing: str, expected: bool) -> None:
    """`ps -A -o pgid=,stat=` lines: only the group's members count, and all must be Z."""
    assert only_zombies(listing, 4242) is expected


@pytest.mark.parametrize(
    ("raised", "expected"),
    [(None, True), (ProcessLookupError(), False), (PermissionError(), True)],
)
def test_group_alive_asks_the_kernel_with_signal_0(
    monkeypatch: pytest.MonkeyPatch, raised: OSError | None, expected: bool
) -> None:
    """killpg(group, 0): no such group means empty; any other answer means members remain."""
    calls: list[tuple[int, int]] = []

    def killpg(group: int, signum: int) -> None:
        calls.append((group, signum))
        if raised is not None:
            raise raised

    monkeypatch.setattr(os, "killpg", killpg)
    assert group_alive(4242) is expected
    assert calls == [(4242, 0)]
