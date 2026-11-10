# SPDX-License-Identifier: MIT

"""The sandbox CDC stack (RUST-1.8): Kafka and Debezium as gluon-local runs them.

A KRaft broker and a standalone Kafka Connect worker with Debezium's Postgres
connector, run from the Maven Central jars gluon `bin/sandbox-setup --only cdc`
installs (Kafka 3.8.0, Debezium 3.0.0.Final: gluon-local's versions). The
connector is the one gluon-local registers
(`infra/k8s/local-infra/debezium-connectors-register.yaml`) with only the
database address and login replaced, so the record on the topic is the one the
cluster would publish. The harness's Postgres already runs `wal_level=logical`.
"""

import contextlib
import logging
import os
import signal
import socket
import subprocess
import time
import urllib.request
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Self

from kafka import KafkaAdminClient, KafkaConsumer, KafkaProducer
from kafka.errors import (
    CoordinatorLoadInProgressError,
    CoordinatorNotAvailableError,
    NotCoordinatorError,
)

from gluon_contract.ports import free_port
from gluon_contract.postgres import PostgresEndpoint
from gluon_contract.routing import load_connector

# kafka-python logs at ERROR what is routine here (a topic nobody has created
# yet, a broker mid-outage); pytest would report those lines as if checks failed.
logging.getLogger("kafka").setLevel(logging.CRITICAL)

HOST = "127.0.0.1"
KAFKA_VERSION = "3.8.0"
DEBEZIUM_VERSION = "3.0.0.Final"
CLUSTER_ID = "MkU3OEVBNTcwNTJENDM2Qk"
"""gluon-local's (infra/k8s/local-infra/kafka.yaml, CLUSTER_ID)."""
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


class CdcError(Exception):
    """The stack couldn't be started; the message says why."""


@dataclass(frozen=True, slots=True)
class Record:
    """One Kafka record, decoded as UTF-8."""

    topic: str
    key: str | None
    value: str | None
    headers: dict[str, str | None]
    """A header written with no value (Debezium's for a NULL field) is None."""


def cdc_home(env: Mapping[str, str], *, home: Path | None = None) -> Path:
    """CONTRACT_CDC_HOME, else where gluon `bin/sandbox-setup --only cdc` puts the jars."""
    if explicit := env.get("CONTRACT_CDC_HOME"):
        return Path(explicit)
    base = Path.home() if home is None else home
    return base / ".local" / f"cdc-kafka-{KAFKA_VERSION}_debezium-{DEBEZIUM_VERSION}"


def _properties(pairs: Mapping[str, str]) -> str:
    return "".join(f"{key}={value}\n" for key, value in pairs.items())


def broker_properties(data_dir: Path, port: int, controller_port: int) -> str:
    """A single-node KRaft broker and controller on loopback."""
    return _properties(
        {
            "process.roles": "broker,controller",
            "node.id": "1",
            "listeners": f"PLAINTEXT://{HOST}:{port},CONTROLLER://{HOST}:{controller_port}",
            "advertised.listeners": f"PLAINTEXT://{HOST}:{port}",
            "controller.listener.names": "CONTROLLER",
            "controller.quorum.voters": f"1@{HOST}:{controller_port}",
            "listener.security.protocol.map": "CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT",
            "log.dirs": str(data_dir),
            "offsets.topic.replication.factor": "1",
            "transaction.state.log.replication.factor": "1",
            "transaction.state.log.min.isr": "1",
            "group.initial.rebalance.delay.ms": "0",
            "num.partitions": "1",
        }
    )


def worker_properties(work_dir: Path, bootstrap: str, rest_port: int, plugin_path: Path) -> str:
    """A standalone Connect worker with gluon-local's converters (StringConverter)."""
    string = "org.apache.kafka.connect.storage.StringConverter"
    return _properties(
        {
            "bootstrap.servers": bootstrap,
            "key.converter": string,
            "value.converter": string,
            "offset.storage.file.filename": str(work_dir / "connect.offsets"),
            "offset.flush.interval.ms": "1000",
            "plugin.path": str(plugin_path),
            "listeners": f"http://{HOST}:{rest_port}",
        }
    )


def connector_properties(
    name: str, registered: Mapping[str, str], endpoint: PostgresEndpoint
) -> str:
    """The registered connector config, pointed at `endpoint`'s database."""
    config = {"name": name, **registered}
    config.update(
        {
            "database.hostname": endpoint.host,
            "database.port": str(endpoint.port),
            "database.dbname": endpoint.login.database,
            "database.user": endpoint.login.user,
            "database.password": endpoint.login.password,
        }
    )
    return _properties(config)


def _port_open(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.5)
        return probe.connect_ex((HOST, port)) == 0


class _Processes:
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
            raise CdcError(
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
                raise CdcError(f"{what} exited with {process.returncode}:\n{self.tail(log)}")
            if time.monotonic() > deadline:
                raise CdcError(f"{what} not ready after {START_TIMEOUT_S}s:\n{self.tail(log)}")
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
            _signal(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=STOP_GRACE_S)
            except subprocess.TimeoutExpired:
                _signal(process.pid, signal.SIGKILL)
                process.wait()
        _signal(process.pid, signal.SIGKILL)
        if process in self._running:
            self._running.remove(process)

    def stop_all(self) -> None:
        """Every process still running, newest first."""
        for process in reversed(list(self._running)):
            self.stop(process)


class KafkaBroker:
    """A single-node KRaft broker for one run; a context manager (RUST-1.8, RUST-6.1).

    `stop()` and `start()` give an outage: the same port and data come back.
    """

    def __init__(self, home: Path, work_dir: Path, *, java: str = "java") -> None:
        """Prepares, but doesn't start, the broker (jars in `home/kafka`)."""
        self._processes = _Processes(home, work_dir, java)
        self.work_dir = work_dir
        self.port = free_port()
        self._controller_port = free_port()
        self._process: subprocess.Popen[bytes] | None = None
        self._formatted = False

    @property
    def bootstrap(self) -> str:
        """The broker's address, for clients."""
        return f"{HOST}:{self.port}"

    def __enter__(self) -> Self:
        """Checks the jars, formats the storage and starts the broker."""
        self._processes.prepare(("kafka",))
        try:
            self.start()
        except BaseException:
            self._processes.stop_all()
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Stops the broker."""
        self._processes.stop_all()

    def start(self) -> None:
        """Starts the broker (formatting its storage the first time) and waits for its port."""
        config = self.work_dir / "server.properties"
        if not self._formatted:
            config.write_text(
                broker_properties(self.work_dir / "kafka-data", self.port, self._controller_port),
                encoding="utf-8",
            )
            argv = self._processes.argv(
                "kafka",
                "256m",
                "kafka.tools.StorageTool",
                "format",
                "-t",
                CLUSTER_ID,
                "-c",
                str(config),
            )
            done = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=120)
            if done.returncode != 0:
                raise CdcError(
                    f"formatting the broker's storage failed: {done.stdout}{done.stderr}"
                )
            self._formatted = True
        self._process = self._processes.spawn(
            self._processes.argv("kafka", "384m", "kafka.Kafka", str(config)), "kafka.log"
        )
        self._processes.wait(
            "the Kafka broker", lambda: _port_open(self.port), self._process, "kafka.log"
        )

    def stop(self) -> None:
        """Stops the broker (an outage); `start()` brings it back."""
        if self._process is not None:
            self._processes.stop(self._process)
            self._process = None

    def produce(
        self, topic: str, key: str | None, value: str | None, headers: Mapping[str, str]
    ) -> None:
        """Sends one record and waits for the broker to take it."""
        producer = KafkaProducer(bootstrap_servers=self.bootstrap)
        try:
            producer.send(
                topic,
                key=None if key is None else key.encode(),
                value=None if value is None else value.encode(),
                headers=[(name, text.encode()) for name, text in headers.items()],
            ).get(timeout=30)
        finally:
            producer.close()

    def record(
        self, topic: str, until: Callable[[Record], bool], *, timeout_s: float = 60.0
    ) -> Record:
        """The first record on `topic` (read from the beginning) that `until` accepts.

        Raises:
            CdcError: none within `timeout_s`, listing what was seen.
        """
        consumer = KafkaConsumer(
            bootstrap_servers=self.bootstrap,
            group_id=f"gluon-contract-{uuid.uuid4().hex[:8]}",
            auto_offset_reset="earliest",
            enable_auto_commit=False,
            consumer_timeout_ms=1000,
        )
        consumer.subscribe([topic])
        seen: list[Record] = []
        deadline = time.monotonic() + timeout_s
        try:
            while time.monotonic() < deadline:
                for message in consumer:
                    record = Record(
                        topic=message.topic,
                        key=None if message.key is None else message.key.decode("utf-8"),
                        value=None if message.value is None else message.value.decode("utf-8"),
                        headers={
                            name: None if value is None else value.decode("utf-8")
                            for name, value in message.headers
                        },
                    )
                    if until(record):
                        return record
                    seen.append(record)
        finally:
            consumer.close()
        raise CdcError(f"no matching record on {topic} after {timeout_s}s; saw {seen[-5:]}")

    def records(self, topic: str, *, settle_s: float = 2.0) -> list[Record]:
        """Every record on `topic` now (reading until nothing new comes for `settle_s`)."""
        found: list[Record] = []

        def keep(record: Record) -> bool:
            found.append(record)
            return False

        with contextlib.suppress(CdcError):
            self.record(topic, keep, timeout_s=settle_s)
        return found

    def committed(self, group: str, topic: str, *, timeout_s: float = 30.0) -> dict[int, int]:
        """The group's committed offsets on `topic`, by partition (retrying while the
        broker's group coordinator comes up)."""
        deadline = time.monotonic() + timeout_s
        admin = KafkaAdminClient(bootstrap_servers=self.bootstrap)
        try:
            while True:
                try:
                    offsets = admin.list_group_offsets({group: None}).get(group, {})
                    break
                except (
                    CoordinatorNotAvailableError,
                    CoordinatorLoadInProgressError,
                    NotCoordinatorError,
                ):
                    if time.monotonic() > deadline:
                        raise
                    time.sleep(0.5)
        finally:
            admin.close()
        return {
            tp.partition: meta.offset
            for tp, meta in offsets.items()
            if tp.topic == topic and meta.offset >= 0
        }


class CdcStack:
    """Broker and Connect worker for one run; a context manager."""

    def __init__(
        self,
        home: Path,
        work_dir: Path,
        postgres: PostgresEndpoint,
        *,
        connector: str = "user-outbox-connector",
        java: str = "java",
    ) -> None:
        """Prepares, but doesn't start, the stack.

        Args:
            home: the jars (`kafka/`, `connect/`, `plugins/`).
            work_dir: data, configuration and logs.
            postgres: the database the connector reads.
            connector: the registered connector's name (its ConfigMap key without `.json`).
            java: the Java launcher.
        """
        self.home = home
        self.work_dir = work_dir
        self._postgres = postgres
        self._connector = connector
        self._processes = _Processes(home, work_dir, java)
        self.broker = KafkaBroker(home, work_dir, java=java)
        self.rest_port = free_port()

    @property
    def bootstrap(self) -> str:
        """The broker's address, for clients."""
        return self.broker.bootstrap

    def __enter__(self) -> Self:
        """Checks the jars, then starts the broker and the worker and waits for streaming."""
        self._processes.prepare(("kafka", "connect", "plugins"))
        try:
            self.broker.__enter__()
            self._start_worker()
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
        """Stops the worker, then the broker."""
        self.stop()

    def _start_worker(self) -> None:
        worker = self.work_dir / "worker.properties"
        worker.write_text(
            worker_properties(self.work_dir, self.bootstrap, self.rest_port, self.home / "plugins"),
            encoding="utf-8",
        )
        connector = self.work_dir / "connector.properties"
        registered = load_connector(f"{self._connector}.json")
        connector.write_text(
            connector_properties(self._connector, registered, self._postgres), encoding="utf-8"
        )
        process = self._processes.spawn(
            self._processes.argv(
                "connect",
                "512m",
                "org.apache.kafka.connect.cli.ConnectStandalone",
                str(worker),
                str(connector),
            ),
            "connect.log",
        )
        self._processes.wait(
            "Debezium's streaming",
            lambda: "Starting streaming" in self._processes.text("connect.log"),
            process,
            "connect.log",
        )

    def restart_connector(self) -> None:
        """Restarts the connector and its tasks over Connect's REST API (as gluon
        bin/k8s-local-up does after an implementation switch), then waits until
        Debezium streams again."""
        streams_before = self._processes.text("connect.log").count("Starting streaming")
        url = (
            f"http://{HOST}:{self.rest_port}/connectors/{self._connector}/restart?includeTasks=true"
        )
        request = urllib.request.Request(url, method="POST")
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read()
        deadline = time.monotonic() + START_TIMEOUT_S
        while self._processes.text("connect.log").count("Starting streaming") <= streams_before:
            if time.monotonic() > deadline:
                raise CdcError(
                    f"the connector didn't stream again after a restart:\n"
                    f"{self._processes.tail('connect.log')}"
                )
            time.sleep(0.25)

    def connector_status(self) -> str:
        """The worker's REST status for the connector, as JSON text."""
        url = f"http://{HOST}:{self.rest_port}/connectors/{self._connector}/status"
        with urllib.request.urlopen(url, timeout=5) as response:
            body: bytes = response.read()
        return body.decode("utf-8")

    def record(
        self, topic: str, until: Callable[[Record], bool], *, timeout_s: float = 60.0
    ) -> Record:
        """As `KafkaBroker.record`."""
        return self.broker.record(topic, until, timeout_s=timeout_s)

    def stop(self) -> None:
        """Stops the worker, then the broker."""
        self._processes.stop_all()
        self.broker.__exit__(None, None, None)


def _signal(group: int, signum: signal.Signals) -> None:
    with contextlib.suppress(ProcessLookupError):
        os.killpg(group, signum)
