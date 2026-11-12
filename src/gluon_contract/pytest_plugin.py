# SPDX-License-Identifier: MIT

"""pytest wiring for the contract checks in `checks/` (RUST-1.2 spec FR8).

`checks/conftest.py` imports these hooks and fixtures. A run is configured by
`CONTRACT_*` variables, overridden by the options below; see `config.py`.
Checks ask for the session-scoped `harness` fixture: the first one to do so
starts Postgres, the OTLP stub and the build under test, and the session's end
stops them. The CDC group also asks for `cdc`, which adds the sandbox CDC stack
(Kafka, Connect, Debezium: `cdc.py`, RUST-1.8) on the harness's Postgres. The
probe group (RUST-6.x) needs no service: `kafka` (a broker of its own) and
`lookup_stub` (user-service's `GET /users/{id}`, scriptable).

A run judges one service (`--service`, default user-service; RPN-3). A check
module marked `pytest.mark.service("<name>")` belongs to that service and is
deselected in a run for any other; an unmarked check is service-neutral.
"""

import os
import shlex
import urllib.request
import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Protocol

import psycopg
import pytest

from gluon_contract.cdc import CdcStack, KafkaBroker, Record, cdc_home
from gluon_contract.cluster import ClusterHarness, ConsoleTopicReader, cluster_settings
from gluon_contract.config import DEFAULT_SERVICE, ConfigError, HarnessConfig, load_config
from gluon_contract.harness import Harness
from gluon_contract.http_stub import HttpStub
from gluon_contract.otlp_stub import OtlpStub
from gluon_contract.ports import free_port
from gluon_contract.probe import probe_env
from gluon_contract.services import KNOWN_SERVICES, UnknownServiceError, profile
from gluon_contract.target import TargetProcess

OPTIONS = {
    "service": "CONTRACT_SERVICE",
    "target_cmd": "CONTRACT_TARGET_CMD",
    "target_cwd": "CONTRACT_TARGET_CWD",
    "target_name": "CONTRACT_TARGET_NAME",
    "cdc_home": "CONTRACT_CDC_HOME",
    "probe_cmd": "CONTRACT_PROBE_CMD",
    "base_url": "CONTRACT_BASE_URL",
}
CLUSTER_SKIP = "needs isolated mode (cluster mode runs only the checks marked cluster)"
SERVICE_MARKER = (
    "service(name, ...): the service(s) whose contract a check is; it runs only in a run "
    "for one of them (--service). Unmarked checks run for any service (RPN-3)"
)


def pytest_configure(config: pytest.Config) -> None:
    """Registers the `service` marker (checks/ runs with --strict-markers too)."""
    config.addinivalue_line("markers", SERVICE_MARKER)


def pytest_addoption(parser: pytest.Parser) -> None:
    """The harness's command-line options; each overrides its CONTRACT_* variable."""
    group = parser.getgroup("gluon-contract", "gluon contract harness")
    group.addoption(
        "--service",
        help=f"the service whose contract the run judges (CONTRACT_SERVICE; default "
        f"{DEFAULT_SERVICE}; known: {', '.join(KNOWN_SERVICES)})",
    )
    group.addoption(
        "--target-cmd", help="command that starts the build under test (CONTRACT_TARGET_CMD)"
    )
    group.addoption("--target-cwd", help="its working directory (CONTRACT_TARGET_CWD)")
    group.addoption("--target-name", help="a label for reports (CONTRACT_TARGET_NAME)")
    group.addoption(
        "--base-url",
        help="cluster mode: the deployed service's URL; nothing is started (CONTRACT_BASE_URL)",
    )
    group.addoption(
        "--probe-cmd",
        help="command that starts the consumer probe, for the probe group (CONTRACT_PROBE_CMD)",
    )
    group.addoption(
        "--cdc-home",
        help="the CDC stack's jars, for the CDC group (CONTRACT_CDC_HOME; default: where "
        "gluon bin/sandbox-setup --only cdc puts them)",
    )
    group.addoption(
        "--keep-artifacts",
        action="store_true",
        help="keep the work directory: logs, Postgres data (CONTRACT_KEEP_ARTIFACTS)",
    )


def raw_settings(config: pytest.Config) -> dict[str, str]:
    """CONTRACT_* variables from the environment, overlaid with the options given."""
    raw = {key: value for key, value in os.environ.items() if key.startswith("CONTRACT_")}
    for option, key in OPTIONS.items():
        value = config.getoption(option)
        if value is not None:
            raw[key] = value
    if config.getoption("keep_artifacts"):
        raw["CONTRACT_KEEP_ARTIFACTS"] = "1"
    return raw


def pytest_report_header(config: pytest.Config) -> str | None:
    """Says which build a run judges, at the top of the report."""
    raw = raw_settings(config)
    command = raw.get("CONTRACT_TARGET_CMD")
    if not command:
        return None
    name = raw.get("CONTRACT_TARGET_NAME") or command.split()[0]
    return f"gluon-contract: target {name} ({command}) as {run_service(raw)}"


@pytest.fixture(scope="session")
def harness_config(pytestconfig: pytest.Config) -> HarnessConfig:
    """The run's configuration; an unusable one ends the session as a usage error."""
    try:
        return load_config(raw_settings(pytestconfig), cwd=Path.cwd())
    except ConfigError as error:
        pytest.exit(str(error), returncode=pytest.ExitCode.USAGE_ERROR)


def run_service(raw: Mapping[str, str]) -> str:
    """The service a run judges: CONTRACT_SERVICE (or --service), else the default."""
    return raw.get("CONTRACT_SERVICE") or DEFAULT_SERVICE


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Keeps the checks of the run's service (and the neutral ones), deselecting the rest;
    in cluster mode, then skips every check not marked `cluster` (or marked `isolated`).

    An unknown service, or a `service` marker naming one, stops the run as a usage error
    before any check starts anything.
    """
    raw = raw_settings(config)
    service = _known_service_or_exit(raw)
    misnamed = [
        f"{item.nodeid}: {marker.args!r}"
        for item in items
        for marker in item.iter_markers("service")
        if not marker.args or not set(marker.args) <= set(KNOWN_SERVICES)
    ]
    if misnamed:
        pytest.exit(
            "service markers must name known services "
            f"({', '.join(KNOWN_SERVICES)}):\n" + "\n".join(f"- {line}" for line in misnamed),
            returncode=pytest.ExitCode.USAGE_ERROR,
        )
    selected: list[pytest.Item] = []
    deselected: list[pytest.Item] = []
    for item in items:
        marker = item.get_closest_marker("service")
        (selected if marker is None or service in marker.args else deselected).append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = selected
    if cluster_settings(raw) is None:
        return
    for item in items:
        if item.get_closest_marker("cluster") is None or item.get_closest_marker("isolated"):
            item.add_marker(pytest.mark.skip(reason=CLUSTER_SKIP))


def _known_service_or_exit(raw: Mapping[str, str]) -> str:
    """The run's service if the harness has a profile for it; else ends the run as a usage
    error, listing every configuration problem in isolated mode (as the harness would)."""
    service = run_service(raw)
    try:
        profile(service)
    except UnknownServiceError as error:
        message = f"Invalid harness configuration:\n- CONTRACT_SERVICE: {error}"
        if cluster_settings(raw) is None:
            try:
                load_config(raw, cwd=Path.cwd())
            except ConfigError as problems:
                message = str(problems)
        pytest.exit(message, returncode=pytest.ExitCode.USAGE_ERROR)
    return service


@pytest.fixture(scope="session")
def harness(pytestconfig: pytest.Config) -> Iterator[Harness | ClusterHarness]:
    """The throwaway world for the whole session, torn down at its end; in cluster mode
    (CONTRACT_BASE_URL) just the deployment's URL."""
    settings = cluster_settings(raw_settings(pytestconfig))
    if settings is not None:
        yield ClusterHarness(settings.base_url)
        return
    try:
        config = load_config(raw_settings(pytestconfig), cwd=Path.cwd())
    except ConfigError as error:
        pytest.exit(str(error), returncode=pytest.ExitCode.USAGE_ERROR)
    with Harness(config) as running:
        yield running


class TopicReader(Protocol):
    """Reads a Kafka topic from the beginning."""

    def record(
        self, topic: str, until: Callable[[Record], bool], *, timeout_s: float = 60.0
    ) -> Record:
        """The first record `until` accepts."""
        ...


@pytest.fixture(scope="session")
def user_events(pytestconfig: pytest.Config, request: pytest.FixtureRequest) -> TopicReader:
    """The topic the service's outbox reaches: the CDC stack's in isolated mode, the
    cluster's (through a console consumer) in cluster mode."""
    settings = cluster_settings(raw_settings(pytestconfig))
    if settings is not None:
        return ConsoleTopicReader(settings.console_consumer)
    stack: CdcStack = request.getfixturevalue("cdc")
    return stack


@pytest.fixture
def db(harness: Harness) -> Iterator[psycopg.Connection[tuple[Any, ...]]]:
    """A connection to the service's own database, as the service logs in (autocommit)."""
    endpoint = harness.postgres.endpoint
    with psycopg.connect(
        host=endpoint.host,
        port=endpoint.port,
        dbname=endpoint.login.database,
        user=endpoint.login.user,
        password=endpoint.login.password,
        autocommit=True,
    ) as connection:
        yield connection


@pytest.fixture(scope="session")
def cdc(harness: Harness, pytestconfig: pytest.Config) -> Iterator[CdcStack]:  # isolated only
    """Kafka, Connect and Debezium on the harness's Postgres, for the session (RUST-1.8)."""
    with CdcStack(
        cdc_home(raw_settings(pytestconfig)), harness.work_dir / "cdc", harness.postgres.endpoint
    ) as stack:
        yield stack


@pytest.fixture(scope="session")
def kafka(
    pytestconfig: pytest.Config, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[KafkaBroker]:
    """A Kafka broker of the session's own (RUST-6.1), from the CDC stack's jars."""
    home = cdc_home(raw_settings(pytestconfig))
    with KafkaBroker(home, tmp_path_factory.mktemp("kafka")) as broker:
        yield broker


@pytest.fixture
def lookup_stub() -> Iterator[HttpStub]:
    """user-service's GET /users/{id}, scriptable (5xx, delays, resets), for one check."""
    with HttpStub() as stub:
        yield stub


class ProbeRun:
    """One started probe: its topic, group, DLQ topic, metrics, spans and log."""

    def __init__(
        self, process: TargetProcess, otlp: OtlpStub, topic: str, group: str, metrics_port: int
    ) -> None:
        self.process = process
        self.otlp = otlp
        self.topic = topic
        self.group = group
        self.dlq_topic = f"{topic}-dlq"
        self.metrics_url = f"http://127.0.0.1:{metrics_port}/metrics"

    def scrape(self) -> str:
        """One scrape of its metrics."""
        with urllib.request.urlopen(self.metrics_url, timeout=5) as response:
            body: bytes = response.read()
        return body.decode("utf-8")


@pytest.fixture
def probe(
    pytestconfig: pytest.Config,
    kafka: KafkaBroker,
    lookup_stub: HttpStub,
    tmp_path: Path,
) -> Iterator[Callable[..., ProbeRun]]:
    """Starts the consumer probe (RUST-6.x) on a topic and group of its own;
    keyword arguments override its env. Stops everything it started."""
    raw = raw_settings(pytestconfig)
    command = raw.get("CONTRACT_PROBE_CMD")
    if not command:
        pytest.exit("the probe group needs --probe-cmd (CONTRACT_PROBE_CMD)", returncode=4)
    started: ExitStack = ExitStack()

    def start(**overrides: str) -> ProbeRun:
        suffix = uuid.uuid4().hex[:8]
        topic, group = f"user-events-{suffix}", f"events-probe-{suffix}"
        otlp = started.enter_context(OtlpStub())
        metrics_port = free_port()
        env = probe_env(
            bootstrap=kafka.bootstrap,
            topic=topic,
            group=group,
            lookup_url=lookup_stub.url,
            metrics_port=metrics_port,
            otlp_endpoint=otlp.endpoint,
            base_env=os.environ,
            **overrides,
        )
        process = started.enter_context(
            TargetProcess(
                argv=shlex.split(command),
                cwd=Path(raw.get("CONTRACT_TARGET_CWD") or Path.cwd()),
                env=env,
                log_file=tmp_path / f"probe-{suffix}.log",
                readiness_url=f"http://127.0.0.1:{metrics_port}/metrics",
                readiness_deadline_s=60.0,
            )
        )
        return ProbeRun(process, otlp, topic, group, metrics_port)

    with started:
        yield start
