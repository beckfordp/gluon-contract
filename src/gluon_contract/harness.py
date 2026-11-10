# SPDX-License-Identifier: MIT

"""One isolated-mode run: Postgres, the OTLP stub and the target together (spec FR6, FR7).

Entering starts them in that order, each addressed to the previous through the
env-var contract; leaving tears them down in reverse, even when a start fails,
and removes the work directory unless keep-artifacts is set.
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

from gluon_contract.config import HarnessConfig
from gluon_contract.env_contract import Endpoints, postgres_login, service_env
from gluon_contract.otlp_stub import OtlpStub
from gluon_contract.ports import free_port
from gluon_contract.postgres import ThrowawayPostgres
from gluon_contract.target import TargetProcess

HOST = "127.0.0.1"


class Harness:
    """The throwaway world one run of the checks uses; a context manager."""

    work_dir: Path
    postgres: ThrowawayPostgres
    otlp: OtlpStub
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
        self._base_env = dict(os.environ if base_env is None else base_env)
        self._work_root = work_root
        self._stack = ExitStack()

    def __enter__(self) -> Self:
        """Starts Postgres, the OTLP stub, then the target; undoes all of it on failure."""
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
            self.endpoints = Endpoints(
                http_port=free_port(),
                metrics_port=free_port(),
                postgres_host=self.postgres.endpoint.host,
                postgres_port=self.postgres.endpoint.port,
                otlp_endpoint=self.otlp.endpoint,
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

    def _close(self) -> None:
        try:
            self._stack.close()
        finally:
            if not self.config.keep_artifacts:
                shutil.rmtree(self.work_dir, ignore_errors=True)
