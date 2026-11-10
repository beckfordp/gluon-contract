# SPDX-License-Identifier: MIT

"""The build under test as a local process (RUST-1.2 spec FR5).

Proven against the stand-in target (a test double), since no implementation of
user-service exists in the sandbox yet.
"""

import json
import sys
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
from processes import processes_mentioning
from stand_in_target import CHILD_MARKER

from gluon_contract.env_contract import Endpoints, service_env
from gluon_contract.otlp_stub import OtlpStub
from gluon_contract.ports import free_port
from gluon_contract.target import LogTimeoutError, TargetError, TargetProcess

STAND_IN = Path(__file__).with_name("stand_in_target.py")


@pytest.fixture
def otlp() -> Iterator[OtlpStub]:
    """The stand-in exports a span at startup, so something must receive it."""
    with OtlpStub() as stub:
        yield stub


def endpoints(otlp: OtlpStub) -> Endpoints:
    """Fresh ports; no database (these tests use /health, which doesn't need one)."""
    return Endpoints(
        http_port=free_port(),
        metrics_port=free_port(),
        postgres_host="127.0.0.1",
        postgres_port=free_port(),
        otlp_endpoint=otlp.endpoint,
    )


def target(
    tmp_path: Path,
    where: Endpoints,
    *flags: str,
    readiness_path: str = "/health",
    deadline_s: float = 20,
    stop_grace_s: float = 10,
) -> TargetProcess:
    """A TargetProcess for the stand-in, started with the user-service env contract."""
    return TargetProcess(
        argv=(sys.executable, str(STAND_IN), *flags),
        cwd=tmp_path,
        env=service_env("user-service", where, base_env={"PATH": "/usr/bin:/bin"}),
        log_file=tmp_path / "target.log",
        readiness_url=f"http://127.0.0.1:{where.http_port}{readiness_path}",
        readiness_deadline_s=deadline_s,
        stop_grace_s=stop_grace_s,
    )


def test_a_started_target_is_ready_logged_and_given_exactly_its_environment(
    tmp_path: Path, otlp: OtlpStub
) -> None:
    """Ready on its readiness path; stdout captured; the environment is exactly the one passed."""
    where = endpoints(otlp)
    process = target(tmp_path, where)
    with process:
        assert process.running
        with urllib.request.urlopen(f"http://127.0.0.1:{where.http_port}/__env") as response:
            received = json.loads(response.read())
        assert received == process.env
        line = process.wait_for_log(lambda text: text.startswith('{"@timestamp"'))
        assert json.loads(line)["message"] == "stand-in started"
    assert not process.running
    assert processes_mentioning(str(STAND_IN)) == []


def test_a_target_that_exits_early_fails_with_its_output(tmp_path: Path, otlp: OtlpStub) -> None:
    """The exit code and the log tail say why, not just 'not ready'."""
    with pytest.raises(TargetError, match="exited with code 3 before it was ready") as raised:
        target(tmp_path, endpoints(otlp), "--exit", "3").__enter__()
    assert "stand-in: exiting as asked" in str(raised.value)


def test_a_target_that_never_gets_ready_fails_at_the_deadline_and_is_stopped(
    tmp_path: Path, otlp: OtlpStub
) -> None:
    """A missed deadline stops the process before raising."""
    process = target(
        tmp_path, endpoints(otlp), "--never-ready", readiness_path="/health/ready", deadline_s=1
    )
    with pytest.raises(TargetError, match=r"not ready after 1(\.0)?s"):
        process.__enter__()
    assert not process.running
    assert processes_mentioning(str(STAND_IN)) == []


def test_stop_escalates_to_sigkill_when_sigterm_is_ignored(tmp_path: Path, otlp: OtlpStub) -> None:
    """SIGTERM first; SIGKILL after the grace period."""
    process = target(tmp_path, endpoints(otlp), "--ignore-sigterm", stop_grace_s=0.5)
    with process:
        pass
    assert process.returncode == -9
    assert processes_mentioning(str(STAND_IN)) == []


def test_stop_takes_the_whole_process_group_with_it(tmp_path: Path, otlp: OtlpStub) -> None:
    """Children the build starts (a JVM launcher's java, say) don't outlive it."""
    with target(tmp_path, endpoints(otlp), "--spawn-child"):
        assert processes_mentioning(CHILD_MARKER)
    assert processes_mentioning(CHILD_MARKER) == []


def test_a_missing_executable_is_a_target_error(tmp_path: Path, otlp: OtlpStub) -> None:
    """A wrong CONTRACT_TARGET_CMD is reported plainly."""
    where = endpoints(otlp)
    process = TargetProcess(
        argv=(str(tmp_path / "no-such-binary"),),
        cwd=tmp_path,
        env=service_env("user-service", where, base_env={}),
        log_file=tmp_path / "target.log",
        readiness_url=f"http://127.0.0.1:{where.http_port}/health",
        readiness_deadline_s=5,
    )
    with pytest.raises(TargetError, match="could not start"):
        process.__enter__()


def test_wait_for_log_fails_at_its_deadline_with_the_log_tail(
    tmp_path: Path, otlp: OtlpStub
) -> None:
    """A log line that never comes is a contract failure listing what was written."""
    with (
        target(tmp_path, endpoints(otlp)) as process,
        pytest.raises(LogTimeoutError, match="stand-in started") as raised,
    ):
        process.wait_for_log(lambda text: "never printed" in text, timeout_s=0.5)
    assert isinstance(raised.value, AssertionError)


def test_a_target_that_was_never_started_stops_and_reads_quietly(tmp_path: Path) -> None:
    """stop() before start() is a no-op; there is no output to read yet."""
    process = TargetProcess(
        argv=("unused",),
        cwd=tmp_path,
        env={},
        log_file=tmp_path / "never.log",
        readiness_url="http://127.0.0.1:9/health",
        readiness_deadline_s=1,
    )
    process.stop()
    assert process.log_lines() == []
    assert process.log_tail() == "(no output)"
    assert not process.running
    assert process.returncode is None
