# SPDX-License-Identifier: MIT

"""Runs the processes a stack is made of (RUST-1.8, gluon TD-45): start one in its own
group with its output in a log, wait until it is ready, stop it with its children.

Today it supervises the Kafka broker (`gluon_contract.kafka`) and the Kafka Connect
worker (`gluon_contract.cdc`); what each runs, and how it tells it is ready, stays
with them.
"""

import contextlib
import os
import signal
import socket
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

HOST = "127.0.0.1"
START_TIMEOUT_S = 90.0
STOP_GRACE_S = 30.0


class StackError(Exception):
    """A stack couldn't be started, or didn't answer in time; the message says why."""


def port_open(port: int) -> bool:
    """Something listens on `port` on loopback."""
    with socket.socket() as probe:
        probe.settimeout(0.5)
        return probe.connect_ex((HOST, port)) == 0


class Supervisor:
    """The processes started for one run, their logs in `work_dir`: spawn, wait until
    ready, stop."""

    def __init__(self, work_dir: Path) -> None:
        self.work_dir = work_dir
        self._running: list[subprocess.Popen[bytes]] = []

    def spawn(self, argv: list[str], log_name: str) -> subprocess.Popen[bytes]:
        """Starts a process in its own group, output to `log_name` (appended)."""
        with (self.work_dir / log_name).open("ab") as log:
            process = subprocess.Popen(
                argv,
                cwd=self.work_dir,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        self._running.append(process)
        return process

    def wait(
        self, what: str, ready: Callable[[], bool], process: subprocess.Popen[bytes], log: str
    ) -> None:
        """Until `ready()`; raises with the log's tail if the process exits or time runs out."""
        deadline = time.monotonic() + START_TIMEOUT_S
        while not ready():
            if process.poll() is not None:
                raise StackError(f"{what} exited with {process.returncode}:\n{self.tail(log)}")
            if time.monotonic() > deadline:
                raise StackError(f"{what} not ready after {START_TIMEOUT_S}s:\n{self.tail(log)}")
            time.sleep(0.25)

    def text(self, log: str) -> str:
        """A log's whole text ('' if none yet)."""
        try:
            return (self.work_dir / log).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    def tail(self, log: str) -> str:
        """A log's last lines."""
        return "\n".join(self.text(log).splitlines()[-20:]) or "(no log)"

    def stop(self, process: subprocess.Popen[bytes]) -> None:
        """SIGTERM to its group, SIGKILL after a grace."""
        if process.poll() is None:
            signal_group(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=STOP_GRACE_S)
            except subprocess.TimeoutExpired:
                signal_group(process.pid, signal.SIGKILL)
                process.wait()
        signal_group(process.pid, signal.SIGKILL)
        if process in self._running:
            self._running.remove(process)

    def stop_all(self) -> None:
        """Every process still running, newest first."""
        for process in reversed(list(self._running)):
            self.stop(process)


def signal_group(group: int, signum: signal.Signals) -> None:
    """`signum` to process group `group`, if it still exists."""
    with contextlib.suppress(ProcessLookupError):
        os.killpg(group, signum)
