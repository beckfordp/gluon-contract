# SPDX-License-Identifier: MIT

"""The build under test, run as a local process (RUST-1.2 spec FR5).

Started with the env-var contract in its own process group, its stdout and
stderr captured to a log file; ready once its readiness URL answers 200. Stop
signals the whole group, so a launcher's children (a JVM under a start script,
say) go with it.
"""

import contextlib
import os
import signal
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import TracebackType
from typing import Self

POLL_INTERVAL_S = 0.1
"""How often readiness is polled; the deadline, not this, bounds the wait."""
LOG_TAIL_LINES = 20


class TargetError(Exception):
    """The build under test couldn't be started, didn't get ready, or exited early."""


class LogTimeoutError(AssertionError):
    """An expected log line didn't appear in time: a contract failure, not a harness error."""


class TargetProcess:
    """The build under test for one run; use as a context manager."""

    def __init__(
        self,
        *,
        argv: Sequence[str],
        cwd: Path,
        env: Mapping[str, str],
        log_file: Path,
        readiness_url: str,
        readiness_deadline_s: float,
        stop_grace_s: float = 10.0,
    ) -> None:
        """Prepares, but doesn't start, the process.

        Args:
            argv: the command line.
            cwd: its working directory.
            env: its complete environment (the env-var contract).
            log_file: where its stdout and stderr go.
            readiness_url: answers 200 once it is ready.
            readiness_deadline_s: how long it gets to become ready.
            stop_grace_s: how long SIGTERM gets before SIGKILL.
        """
        self.argv = tuple(argv)
        self.cwd = cwd
        self.env = dict(env)
        self.log_file = log_file
        self.readiness_url = readiness_url
        self.readiness_deadline_s = readiness_deadline_s
        self.stop_grace_s = stop_grace_s
        self._process: subprocess.Popen[bytes] | None = None

    @property
    def running(self) -> bool:
        """Whether the process has been started and hasn't exited."""
        return self._process is not None and self._process.poll() is None

    @property
    def returncode(self) -> int | None:
        """Its exit status once it has exited (negative: killed by that signal)."""
        return None if self._process is None else self._process.poll()

    def __enter__(self) -> Self:
        """Starts the process and waits until it is ready; stops it if it isn't."""
        self.start()
        try:
            self.wait_until_ready()
        except BaseException:
            self.stop()
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Stops the process group."""
        self.stop()

    def start(self) -> None:
        """Starts the process in a new session (its own process group)."""
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        with self.log_file.open("wb") as log:
            try:
                self._process = subprocess.Popen(
                    self.argv,
                    cwd=self.cwd,
                    env=self.env,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            except OSError as error:
                raise TargetError(f"could not start {self.argv[0]}: {error}") from error

    def wait_until_ready(self) -> None:
        """Polls the readiness URL until it answers 200, the process exits, or the deadline.

        Raises:
            TargetError: with the exit code or the deadline, and the log tail.
        """
        deadline = time.monotonic() + self.readiness_deadline_s
        while True:
            code = self.returncode
            if code is not None:
                raise TargetError(
                    f"{self.argv[0]} exited with code {code} before it was ready\n"
                    f"--- {self.log_file} ---\n{self.log_tail()}"
                )
            if self._ready():
                return
            if time.monotonic() >= deadline:
                raise TargetError(
                    f"{self.argv[0]} not ready after {self.readiness_deadline_s}s: "
                    f"GET {self.readiness_url} never answered 200\n"
                    f"--- {self.log_file} ---\n{self.log_tail()}"
                )
            time.sleep(POLL_INTERVAL_S)

    def stop(self) -> None:
        """SIGTERM to the group, SIGKILL after the grace period; always leaves no member alive."""
        if self._process is None:
            return
        group = self._process.pid
        if self._process.poll() is None:
            self._signal_group(group, signal.SIGTERM)
            try:
                self._process.wait(timeout=self.stop_grace_s)
            except subprocess.TimeoutExpired:
                self._signal_group(group, signal.SIGKILL)
                self._process.wait()
        # Children that outlived the leader (or ignored SIGTERM) go too.
        self._signal_group(group, signal.SIGKILL)

    def log_lines(self) -> list[str]:
        """Everything the process has written so far, line by line."""
        try:
            return self.log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        except FileNotFoundError:
            return []

    def wait_for_log(self, predicate: Callable[[str], bool], *, timeout_s: float = 10.0) -> str:
        """Polls the captured output until a line matches; returns the first that does.

        Output is written asynchronously (a process may be ready before it logs),
        so checks wait for lines rather than reading once.

        Raises:
            LogTimeoutError: if no line matches within `timeout_s`, with the log tail.
        """
        deadline = time.monotonic() + timeout_s
        while True:
            match = next((line for line in self.log_lines() if predicate(line)), None)
            if match is not None:
                return match
            if time.monotonic() >= deadline:
                raise LogTimeoutError(
                    f"no matching log line after {timeout_s}s\n"
                    f"--- {self.log_file} ---\n{self.log_tail()}"
                )
            time.sleep(POLL_INTERVAL_S)

    def log_tail(self) -> str:
        """The last lines of its output, for error messages."""
        return "\n".join(self.log_lines()[-LOG_TAIL_LINES:]) or "(no output)"

    def _ready(self) -> bool:
        try:
            with urllib.request.urlopen(self.readiness_url, timeout=1) as response:
                status: int = response.status
        except (urllib.error.URLError, OSError):
            return False
        return status == 200

    @staticmethod
    def _signal_group(group: int, signum: signal.Signals) -> None:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(group, signum)
