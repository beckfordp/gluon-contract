# SPDX-License-Identifier: MIT

"""The sandbox CDC stack (RUST-1.8): Kafka Connect and Debezium as gluon-local runs them.

A standalone Kafka Connect worker with Debezium's Postgres connector, beside a
`gluon_contract.kafka` broker, both run by `gluon_contract.supervisor` (gluon
TD-45). The connector is the one gluon-local registers
(`infra/k8s/local-infra/debezium-connectors-register.yaml`) with only the
database address and login replaced, so the record on the topic is the one the
cluster would publish. The harness's Postgres already runs `wal_level=logical`.
"""

import time
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path
from types import TracebackType
from typing import Self

from gluon_contract.kafka import KAFKA_VERSION, Jars, KafkaBroker, Record, properties_text
from gluon_contract.ports import free_port
from gluon_contract.postgres import PostgresEndpoint
from gluon_contract.routing import load_connector
from gluon_contract.supervisor import HOST, START_TIMEOUT_S, StackError, Supervisor

DEBEZIUM_VERSION = "3.0.0.Final"
"""gluon-local's; installed beside Kafka by gluon `bin/sandbox-setup --only cdc`."""


def cdc_home(env: Mapping[str, str], *, home: Path | None = None) -> Path:
    """CONTRACT_CDC_HOME, else where gluon `bin/sandbox-setup --only cdc` puts the jars."""
    if explicit := env.get("CONTRACT_CDC_HOME"):
        return Path(explicit)
    base = Path.home() if home is None else home
    return base / ".local" / f"cdc-kafka-{KAFKA_VERSION}_debezium-{DEBEZIUM_VERSION}"


def worker_properties(work_dir: Path, bootstrap: str, rest_port: int, plugin_path: Path) -> str:
    """A standalone Connect worker with gluon-local's converters (StringConverter)."""
    string = "org.apache.kafka.connect.storage.StringConverter"
    return properties_text(
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
    return properties_text(config)


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
        self._jars = Jars(home, work_dir, java)
        self._supervisor = Supervisor(work_dir)
        self.broker = KafkaBroker(home, work_dir, java=java)
        self.rest_port = free_port()

    @property
    def bootstrap(self) -> str:
        """The broker's address, for clients."""
        return self.broker.bootstrap

    def __enter__(self) -> Self:
        """Checks the jars, then starts the broker and the worker and waits for streaming."""
        self._jars.prepare(("kafka", "connect", "plugins"))
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
        process = self._supervisor.spawn(
            self._jars.argv(
                "connect",
                "512m",
                "org.apache.kafka.connect.cli.ConnectStandalone",
                str(worker),
                str(connector),
            ),
            "connect.log",
        )
        self._supervisor.wait(
            "Debezium's streaming",
            lambda: "Starting streaming" in self._supervisor.text("connect.log"),
            process,
            "connect.log",
        )

    def restart_connector(self) -> None:
        """Restarts the connector and its tasks over Connect's REST API (as gluon
        bin/k8s-local-up does after an implementation switch), then waits until
        Debezium streams again."""
        streams_before = self._supervisor.text("connect.log").count("Starting streaming")
        url = (
            f"http://{HOST}:{self.rest_port}/connectors/{self._connector}/restart?includeTasks=true"
        )
        request = urllib.request.Request(url, method="POST")
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read()
        deadline = time.monotonic() + START_TIMEOUT_S
        while self._supervisor.text("connect.log").count("Starting streaming") <= streams_before:
            if time.monotonic() > deadline:
                raise StackError(
                    f"the connector didn't stream again after a restart:\n"
                    f"{self._supervisor.tail('connect.log')}"
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
        self._supervisor.stop_all()
        self.broker.__exit__(None, None, None)
