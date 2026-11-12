# SPDX-License-Identifier: MIT

"""One isolated-mode run: Postgres, the OTLP stub and the target together (spec FR6, FR7).

Entering starts them in that order, each addressed to the previous through the
env-var contract; leaving tears them down in reverse, even when a start fails,
and removes the work directory unless keep-artifacts is set. A service whose
profile (`services.py`) asks for more gets it before the target starts: a Kafka
broker with its topics created, and a scriptable stub per service it calls
(RPN-3 FR4).
"""

import os
import shutil
import tempfile
import urllib.request
from collections.abc import Mapping
from contextlib import ExitStack
from pathlib import Path
from types import TracebackType
from typing import Self

from gluon_contract.cdc import KafkaBroker, cdc_home
from gluon_contract.config import HarnessConfig
from gluon_contract.env_contract import Endpoints, postgres_login, service_env
from gluon_contract.http_stub import HttpStub
from gluon_contract.otlp_stub import OtlpStub
from gluon_contract.ports import free_port
from gluon_contract.postgres import ThrowawayPostgres
from gluon_contract.services import ServiceProfile, profile
from gluon_contract.target import TargetProcess

HOST = "127.0.0.1"


class Harness:
    """The throwaway world one run of the checks uses; a context manager."""

    work_dir: Path
    postgres: ThrowawayPostgres
    otlp: OtlpStub
    kafka: KafkaBroker | None
    """The service's broker, if its profile reads Kafka."""
    stubs: dict[str, HttpStub]
    """A stub per service it calls, by service name (scripted by the checks that need it)."""
    endpoints: Endpoints
    target: TargetProcess

    def __init__(
        self,
        config: HarnessConfig,
        *,
        base_env: Mapping[str, str] | None = None,
        work_root: Path | None = None,
    ) -> None:
        """Prepares, but doesn't start, a run.

        Args:
            config: the run's configuration.
            base_env: the environment to take the minimal base from (default: this process's).
            work_root: where to create the work directory (default: the system temp dir).
        """
        self.config = config
        self.profile: ServiceProfile = profile(config.service)
        self.kafka = None
        self.stubs = {}
        self._base_env = dict(os.environ if base_env is None else base_env)
        self._work_root = work_root
        self._stack = ExitStack()

    def __enter__(self) -> Self:
        """Starts Postgres, the OTLP stub, the profile's broker and stubs, then the target;
        undoes all of it on failure."""
        self.work_dir = Path(tempfile.mkdtemp(prefix="gluon-contract-", dir=self._work_root))
        try:
            self.postgres = self._stack.enter_context(
                ThrowawayPostgres(
                    self.config.pg_bin,
                    self.work_dir,
                    postgres_login(self.config.service),
                    keep=self.config.keep_artifacts,
                )
            )
            self.otlp = self._stack.enter_context(OtlpStub())
            if self.profile.kafka:
                self.kafka = self._stack.enter_context(
                    KafkaBroker(self._kafka_home(), self.work_dir / "kafka")
                )
                self.kafka.create_topics(self.profile.topics)
            for called in self.profile.calls:
                self.stubs[called] = self._stack.enter_context(HttpStub())
            self.endpoints = Endpoints(
                http_port=free_port(),
                metrics_port=free_port(),
                postgres_host=self.postgres.endpoint.host,
                postgres_port=self.postgres.endpoint.port,
                otlp_endpoint=self.otlp.endpoint,
                kafka_bootstrap=None if self.kafka is None else self.kafka.bootstrap,
                service_urls={name: stub.url for name, stub in self.stubs.items()},
            )
            self.target = self._stack.enter_context(
                TargetProcess(
                    argv=self.config.target_argv,
                    cwd=self.config.target_cwd,
                    env=service_env(self.config.service, self.endpoints, base_env=self._base_env),
                    log_file=self.work_dir / "target.log",
                    readiness_url=self.base_url + self.config.readiness_path,
                    readiness_deadline_s=self.config.readiness_deadline_s,
                )
            )
        except BaseException:
            self._close()
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Stops everything in reverse order and removes the work directory."""
        self._close()

    @property
    def base_url(self) -> str:
        """The target's HTTP API, e.g. `http://127.0.0.1:38411`."""
        return f"http://{HOST}:{self.endpoints.http_port}"

    @property
    def metrics_url(self) -> str:
        """The target's Prometheus endpoint."""
        return f"http://{HOST}:{self.endpoints.metrics_port}/metrics"

    def scrape_metrics(self) -> str:
        """One scrape of the target's `/metrics`, as text."""
        with urllib.request.urlopen(self.metrics_url, timeout=5) as response:
            body: bytes = response.read()
        return body.decode("utf-8")

    def log_lines(self) -> list[str]:
        """The target's stdout and stderr so far."""
        return self.target.log_lines()

    def _kafka_home(self) -> Path:
        """The broker's jars: the config's, else the CDC group's default lookup."""
        return self.config.kafka_home or cdc_home(self._base_env)

    def _close(self) -> None:
        try:
            self._stack.close()
        finally:
            if not self.config.keep_artifacts:
                shutil.rmtree(self.work_dir, ignore_errors=True)
