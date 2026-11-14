# SPDX-License-Identifier: MIT

"""Java processes for the local stacks (RUST-1.8, gluon TD-45): the Kafka broker
(`gluon_contract.kafka`) and Kafka Connect with Debezium (`gluon_contract.cdc`).

Both run from the Maven Central jars gluon `bin/sandbox-setup --only cdc` installs
(Kafka 3.8.0, Debezium 3.0.0.Final: gluon-local's versions), each process in its own
group so a stop takes its children with it.
"""

import contextlib
import os
import signal
import socket
import subprocess
import time
from collections.abc import Callable, Mapping
from pathlib import Path

HOST = "127.0.0.1"
KAFKA_VERSION = "3.8.0"
DEBEZIUM_VERSION = "3.0.0.Final"
START_TIMEOUT_S = 90.0
STOP_GRACE_S = 30.0
LOG4J = """\
log4j.rootLogger=INFO, stdout
log4j.appender.stdout=org.apache.log4j.ConsoleAppender
log4j.appender.stdout.layout=org.apache.log4j.PatternLayout
log4j.appender.stdout.layout.ConversionPattern=[%d] %p %m (%c)%n
log4j.logger.org.apache.kafka=WARN
log4j.logger.kafka=WARN
log4j.logger.org.reflections=ERROR
log4j.logger.io.debezium=INFO
"""


class StackError(Exception):
    """A stack couldn't be started, or didn't answer in time; the message says why."""


def cdc_home(env: Mapping[str, str], *, home: Path | None = None) -> Path:
    """CONTRACT_CDC_HOME, else where gluon `bin/sandbox-setup --only cdc` puts the jars."""
    if explicit := env.get("CONTRACT_CDC_HOME"):
        return Path(explicit)
    base = Path.home() if home is None else home
    return base / ".local" / f"cdc-kafka-{KAFKA_VERSION}_debezium-{DEBEZIUM_VERSION}"


def properties_text(pairs: Mapping[str, str]) -> str:
    """`pairs` as a .properties text."""
    return "".join(f"{key}={value}\n" for key, value in pairs.items())


def port_open(port: int) -> bool:
    """Something listens on `port` on loopback."""
    with socket.socket() as probe:
        probe.settimeout(0.5)
        return probe.connect_ex((HOST, port)) == 0


class JavaProcesses:
    """Java processes started for one run: spawn, wait until ready, stop."""

    def __init__(self, home: Path, work_dir: Path, java: str) -> None:
        self.home = home
        self.work_dir = work_dir
        self._java = java
        self._running: list[subprocess.Popen[bytes]] = []

    def prepare(self, needed: tuple[str, ...]) -> None:
        """Checks the jars and writes the logging config."""
        missing = [name for name in needed if not (self.home / name).is_dir()]
        if missing:
            raise StackError(
                f"no CDC jars in {self.home} (missing {', '.join(missing)}): run gluon "
                "bin/sandbox-setup --only cdc, or set CONTRACT_CDC_HOME"
            )
        self.work_dir.mkdir(parents=True, exist_ok=True)
        (self.work_dir / "log4j.properties").write_text(LOG4J, encoding="utf-8")

    def argv(self, jars: str, heap: str, main: str, *args: str) -> list[str]:
        """A `java` command line on one jar set."""
        return [
            self._java,
            "-Xms64m",
            f"-Xmx{heap}",
            f"-Dlog4j.configuration=file:{self.work_dir / 'log4j.properties'}",
            "-cp",
            str(self.home / jars / "*"),
            main,
            *args,
        ]

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
