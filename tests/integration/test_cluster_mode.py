# SPDX-License-Identifier: MIT

"""Cluster mode end to end (RUST-5.4, prepared): the checks marked `cluster`, run with
CONTRACT_BASE_URL against an already running service (the Rust build, standing in for
a gluon-local deployment) and its outbox published by the sandbox CDC stack, read
through a console consumer command. Needs the CDC jars; skipped, visibly, without them.
"""

import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from gluon_contract.cdc import CdcStack, cdc_home
from gluon_contract.env_contract import Endpoints, postgres_login, service_env
from gluon_contract.ports import free_port
from gluon_contract.postgres import ThrowawayPostgres
from gluon_contract.target import TargetProcess

HOME = cdc_home(os.environ)
REPO = Path(__file__).resolve().parents[2]
RUST = REPO.parents[1] / "services" / "user-service-rs"
BINARY = RUST / "target" / "debug" / "user-service"
pytestmark = pytest.mark.skipif(
    not (HOME / "COMPLETE").is_file() or not BINARY.is_file(),
    reason=f"needs the CDC jars in {HOME} and a built {BINARY}",
)


def test_the_cluster_checks_pass_against_a_running_service(pg_bin: Path, tmp_path: Path) -> None:
    """Only the `cluster` checks run; everything else is skipped as isolated-only."""
    with ThrowawayPostgres(pg_bin, tmp_path, postgres_login("user-service")) as pg:
        port = free_port()
        endpoints = Endpoints(port, free_port(), pg.endpoint.host, pg.endpoint.port, "")
        env = service_env("user-service", endpoints, base_env=os.environ)
        with (
            TargetProcess(
                argv=[str(BINARY)],
                cwd=RUST,
                env=env,
                log_file=tmp_path / "service.log",
                readiness_url=f"http://127.0.0.1:{port}/health/ready",
                readiness_deadline_s=60,
            ),
            CdcStack(HOME, tmp_path / "cdc", pg.endpoint) as cdc,
        ):
            consumer = shlex.join(
                [
                    "java",
                    "-cp",
                    str(HOME / "kafka" / "*"),
                    f"-Dlog4j.configuration=file:{tmp_path / 'cdc' / 'log4j.properties'}",
                    "org.apache.kafka.tools.consumer.ConsoleConsumer",
                    "--bootstrap-server",
                    cdc.bootstrap,
                ]
            )
            done = subprocess.run(
                [sys.executable, "-m", "pytest", "checks", "-p", "no:cacheprovider", "-q", "-rA"],
                cwd=REPO,
                env={
                    **os.environ,
                    "CONTRACT_BASE_URL": f"http://127.0.0.1:{port}",
                    "CONTRACT_KAFKA_CONSOLE_CONSUMER": consumer,
                },
                capture_output=True,
                text=True,
                timeout=900,
                check=False,
            )
    output = done.stdout
    assert done.returncode == 0, output[-3000:]
    passed = [line for line in output.splitlines() if line.startswith("PASSED ")]
    assert any(
        "test_user_cdc.py::test_a_signup_reaches_user_events_in_its_trace" in p for p in passed
    )
    assert any("test_user_rest.py::" in p for p in passed)
    assert any("test_user_docs.py::test_the_openapi_spec_is_the_scala_one" in p for p in passed)
    assert "SKIPPED" in output
    assert "isolated mode" in output
