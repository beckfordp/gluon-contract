# SPDX-License-Identifier: MIT

"""A single-node KRaft Kafka broker for one run (RUST-1.8, RUST-6.1; gluon TD-45).

The CDC stack (`gluon_contract.cdc`) runs one under Kafka Connect; the consumer probe's
checks and notification-service's harness use one on its own.
"""

import contextlib
import logging
import subprocess
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Self

from kafka import KafkaAdminClient, KafkaConsumer, KafkaProducer, TopicPartition
from kafka.consumer.fetcher import ConsumerRecord
from kafka.errors import (
    CoordinatorLoadInProgressError,
    CoordinatorNotAvailableError,
    NotCoordinatorError,
    RetriableError,
    TopicAlreadyExistsError,
)

from gluon_contract.ports import free_port
from gluon_contract.supervisor import HOST, StackError, Supervisor, port_open

# kafka-python logs at ERROR what is routine here (a topic nobody has created
# yet, a broker mid-outage); pytest would report those lines as if checks failed.
logging.getLogger("kafka").setLevel(logging.CRITICAL)

KAFKA_VERSION = "3.8.0"
"""gluon-local's; the jars gluon `bin/sandbox-setup --only cdc` installs."""
CLUSTER_ID = "MkU3OEVBNTcwNTJENDM2Qk"
"""gluon-local's (infra/k8s/local-infra/kafka.yaml, CLUSTER_ID)."""
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


def properties_text(pairs: Mapping[str, str]) -> str:
    """`pairs` as a .properties text."""
    return "".join(f"{key}={value}\n" for key, value in pairs.items())


class Jars:
    """The installed Kafka jar sets (`home/<set>`), and a `java` command line on one,
    logging per `LOG4J` from `work_dir`."""

    def __init__(self, home: Path, work_dir: Path, java: str) -> None:
        self.home = home
        self.work_dir = work_dir
        self._java = java

    def prepare(self, needed: tuple[str, ...]) -> None:
        """Checks the jar sets are installed and writes the logging config."""
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


@dataclass(frozen=True, slots=True)
class Record:
    """One Kafka record, decoded as UTF-8."""

    topic: str
    key: str | None
    value: str | None
    headers: dict[str, str | None]
    """A header written with no value (Debezium's for a NULL field) is None."""


def broker_properties(data_dir: Path, port: int, controller_port: int) -> str:
    """A single-node KRaft broker and controller on loopback."""
    return properties_text(
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


class KafkaBroker:
    """A single-node KRaft broker for one run; a context manager (RUST-1.8, RUST-6.1).

    `stop()` and `start()` give an outage: the same port and data come back.
    """

    def __init__(self, home: Path, work_dir: Path, *, java: str = "java") -> None:
        """Prepares, but doesn't start, the broker (jars in `home/kafka`)."""
        self._jars = Jars(home, work_dir, java)
        self._supervisor = Supervisor(work_dir)
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
        self._jars.prepare(("kafka",))
        try:
            self.start()
        except BaseException:
            self._supervisor.stop_all()
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Stops the broker."""
        self._supervisor.stop_all()

    def start(self) -> None:
        """Starts the broker (formatting its storage the first time) and waits for its port."""
        config = self.work_dir / "server.properties"
        if not self._formatted:
            config.write_text(
                broker_properties(self.work_dir / "kafka-data", self.port, self._controller_port),
                encoding="utf-8",
            )
            argv = self._jars.argv(
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
                raise StackError(
                    f"formatting the broker's storage failed: {done.stdout}{done.stderr}"
                )
            self._formatted = True
        self._process = self._supervisor.spawn(
            self._jars.argv("kafka", "384m", "kafka.Kafka", str(config)), "kafka.log"
        )
        self._supervisor.wait(
            "the Kafka broker", lambda: port_open(self.port), self._process, "kafka.log"
        )

    def stop(self) -> None:
        """Stops the broker (an outage); `start()` brings it back."""
        if self._process is not None:
            self._supervisor.stop(self._process)
            self._process = None

    def create_topics(self, topics: Sequence[str], *, timeout_s: float = 60.0) -> None:
        """Creates each of `topics` not there yet: one partition, replication 1, as the
        notification-service capture's CAPTURE.sh creates its input topics. Returns once
        each has a leader.

        Retried while the broker isn't ready, and when a topic appears between listing
        and creating (a client's auto-create), until `timeout_s`.

        Raises:
            StackError: the topics still couldn't be created at the deadline.
        """
        deadline = time.monotonic() + timeout_s
        while True:
            budget_ms = max(1000, int((deadline - time.monotonic()) * 1000))
            try:
                self._create_missing(topics, budget_ms)
                return
            except (RetriableError, TopicAlreadyExistsError) as error:
                if time.monotonic() >= deadline:
                    raise StackError(
                        f"couldn't create topics {', '.join(topics)} on {self.bootstrap} "
                        f"within {timeout_s}s: {error}"
                    ) from error
                time.sleep(0.5)

    def _create_missing(self, topics: Sequence[str], timeout_ms: int) -> None:
        """One attempt: list the topics, create the missing ones, wait for their leaders."""
        admin = KafkaAdminClient(
            bootstrap_servers=self.bootstrap,
            bootstrap_timeout_ms=timeout_ms,
            request_timeout_ms=timeout_ms,
        )
        try:
            existing = set(admin.list_topics())
            missing = {
                topic: {"num_partitions": 1, "replication_factor": 1}
                for topic in topics
                if topic not in existing
            }
            if missing:
                admin.create_topics(missing, wait_for_metadata=True)
        finally:
            admin.close()

    def produce(
        self, topic: str, key: str | None, value: str | None, headers: Mapping[str, str]
    ) -> int:
        """Sends one record and waits for the broker to take it; returns its offset."""
        producer = KafkaProducer(bootstrap_servers=self.bootstrap)
        try:
            metadata = producer.send(
                topic,
                key=None if key is None else key.encode(),
                value=None if value is None else value.encode(),
                headers=[(name, text.encode()) for name, text in headers.items()],
            ).get(timeout=30)
        finally:
            producer.close()
        offset: int = metadata.offset
        return offset

    def has_group(self, group: str) -> bool:
        """Whether consumer group `group` exists: a consumer has joined it, whether or not
        it has committed (and it stays after the consumer leaves)."""
        admin = KafkaAdminClient(bootstrap_servers=self.bootstrap)
        try:
            return any(listed.get("group_id") == group for listed in admin.list_groups())
        finally:
            admin.close()

    def record(
        self, topic: str, until: Callable[[Record], bool], *, timeout_s: float = 60.0
    ) -> Record:
        """The first record on `topic` (read from the beginning) that `until` accepts.

        Raises:
            StackError: none within `timeout_s`, listing what was seen.
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
                    record = decoded(message)
                    if until(record):
                        return record
                    seen.append(record)
        finally:
            consumer.close()
        raise StackError(f"no matching record on {topic} after {timeout_s}s; saw {seen[-5:]}")

    def records_now(self, topic: str, *, timeout_s: float = 30.0) -> list[Record]:
        """Every record on `topic` up to its end offsets as of the call, in order, without
        waiting for it to settle (a consumer check reads a topic its record's commit has
        made final: RPN-10); none if nobody has written to it.

        Raises:
            StackError: the end wasn't reached within `timeout_s`.
        """
        consumer = KafkaConsumer(bootstrap_servers=self.bootstrap, enable_auto_commit=False)
        try:
            partitions = consumer.partitions_for_topic(topic) or set()
            assigned = [TopicPartition(topic, partition) for partition in sorted(partitions)]
            if not assigned:
                return []
            consumer.assign(assigned)
            consumer.seek_to_beginning(*assigned)
            end = consumer.end_offsets(assigned)
            found: list[Record] = []
            deadline = time.monotonic() + timeout_s
            while any(consumer.position(tp) < end[tp] for tp in assigned):
                if time.monotonic() >= deadline:
                    raise StackError(f"didn't read {topic} to its end within {timeout_s}s")
                for messages in consumer.poll(timeout_ms=500).values():
                    found.extend(decoded(message) for message in messages)
            return found
        finally:
            consumer.close()

    def records(self, topic: str, *, settle_s: float = 2.0) -> list[Record]:
        """Every record on `topic` now (reading until nothing new comes for `settle_s`)."""
        found: list[Record] = []

        def keep(record: Record) -> bool:
            found.append(record)
            return False

        with contextlib.suppress(StackError):
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


def decoded(message: ConsumerRecord) -> Record:
    """A kafka-python message as a `Record`, decoded as UTF-8 (a header written with no
    value stays None)."""
    return Record(
        topic=message.topic,
        key=None if message.key is None else message.key.decode("utf-8"),
        value=None if message.value is None else message.value.decode("utf-8"),
        headers={
            name: None if value is None else value.decode("utf-8")
            for name, value in message.headers
        },
    )
