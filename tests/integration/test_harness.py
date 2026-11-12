# SPDX-License-Identifier: MIT

"""The harness: Postgres, the OTLP stub and the target, up and down together (spec FR6, FR7);
for a service that needs them, a broker and a stub per called service too (RPN-3 FR4).

Proven against the stand-in target (a test double).
"""

import json
import os
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from kafka import KafkaAdminClient
from processes import processes_mentioning

from gluon_contract.cdc import CdcError, cdc_home
from gluon_contract.config import HarnessConfig
from gluon_contract.env_contract import service_env
from gluon_contract.harness import Harness
from gluon_contract.target import TargetError

STAND_IN = Path(__file__).with_name("stand_in_target.py")
BASE_ENV = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LANG": "C.UTF-8", "LEAK": "secret"}
USER_ID = "11111111-1111-4111-8111-111111111111"
ORDER_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
CDC_HOME = cdc_home(os.environ)
needs_kafka_jars = pytest.mark.skipif(
    not (CDC_HOME / "COMPLETE").is_file(),
    reason=f"no CDC jars in {CDC_HOME} (bin/sandbox-setup --only cdc)",
)


def config(pg_bin: Path, tmp_path: Path, *flags: str, keep: bool = False) -> HarnessConfig:
    """The stand-in, as a run would be configured for user-service."""
    return HarnessConfig(
        target_argv=(sys.executable, str(STAND_IN), *flags),
        target_cwd=tmp_path,
        target_name="stand-in",
        service="user-service",
        pg_bin=pg_bin,
        readiness_path="/health/ready",
        readiness_deadline_s=30,
        keep_artifacts=keep,
    )


def notification_config(pg_bin: Path, tmp_path: Path, kafka_home: Path) -> HarnessConfig:
    """The stand-in, as a run would be configured for notification-service."""
    return HarnessConfig(
        target_argv=(sys.executable, str(STAND_IN), "--service", "notification-service"),
        target_cwd=tmp_path,
        target_name="stand-in",
        service="notification-service",
        pg_bin=pg_bin,
        readiness_path="/health/ready",
        readiness_deadline_s=30,
        keep_artifacts=False,
        kafka_home=kafka_home,
    )


def get(url: str) -> tuple[int, bytes]:
    """One GET: its status and body, whatever the status."""
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            status: int = response.status
            return status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def port_closed(port: int) -> bool:
    """Nothing accepts connections on 127.0.0.1:port."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return False
    except OSError:
        return True


def test_the_target_gets_exactly_the_env_contract(pg_bin: Path, tmp_path: Path) -> None:
    """The ports and addresses the harness chose, the minimal base, nothing else (no LEAK)."""
    with Harness(config(pg_bin, tmp_path), base_env=BASE_ENV, work_root=tmp_path) as harness:
        with urllib.request.urlopen(f"{harness.base_url}/__env") as response:
            received = json.loads(response.read())
        assert received == service_env("user-service", harness.endpoints, base_env=BASE_ENV)
        assert "LEAK" not in received
        assert harness.endpoints.otlp_endpoint == harness.otlp.endpoint
        assert harness.endpoints.postgres_port == harness.postgres.endpoint.port


def test_logs_spans_metrics_and_the_database_are_wired(pg_bin: Path, tmp_path: Path) -> None:
    """Ready means the target reached Postgres over TCP; its span, log line and metrics arrive."""
    with Harness(config(pg_bin, tmp_path), base_env=BASE_ENV, work_root=tmp_path) as harness:
        (span,) = harness.otlp.wait_for_spans(lambda s: s.name == "stand-in.start")
        assert span.service_name == "user-service"
        assert harness.target.wait_for_log(lambda text: text.startswith('{"@timestamp"'))
        assert any(line.startswith('{"@timestamp"') for line in harness.log_lines())
        assert "stand_in_up 1" in harness.scrape_metrics()


def test_nothing_survives_a_run(pg_bin: Path, tmp_path: Path) -> None:
    """No work directory, no Postgres, no target, no OTLP listener afterwards."""
    with Harness(config(pg_bin, tmp_path), base_env=BASE_ENV, work_root=tmp_path) as harness:
        work_dir, otlp_port = harness.work_dir, harness.otlp.port
        assert processes_mentioning(str(work_dir))
    assert not work_dir.exists()
    assert processes_mentioning(str(work_dir)) == []
    assert processes_mentioning(str(STAND_IN)) == []
    assert port_closed(otlp_port)


def test_a_failed_start_tears_everything_down(pg_bin: Path, tmp_path: Path) -> None:
    """The target's failure propagates; Postgres and the stub stop; the work directory goes."""
    harness = Harness(
        config(pg_bin, tmp_path, "--exit", "3"), base_env=BASE_ENV, work_root=tmp_path
    )
    with pytest.raises(TargetError, match="exited with code 3"):
        harness.__enter__()
    assert list(tmp_path.glob("gluon-contract-*")) == []
    assert processes_mentioning(str(tmp_path)) == []


def test_keep_artifacts_leaves_the_work_directory(pg_bin: Path, tmp_path: Path) -> None:
    """With keep-artifacts the logs and data stay for inspection; the processes still stop."""
    keep = config(pg_bin, tmp_path, keep=True)
    with Harness(keep, base_env=BASE_ENV, work_root=tmp_path) as harness:
        work_dir = harness.work_dir
    assert (work_dir / "target.log").is_file()
    assert (work_dir / "postgres.log").is_file()
    assert (work_dir / "postgres-data" / "PG_VERSION").is_file()
    assert processes_mentioning(str(work_dir)) == []


def test_user_service_gets_no_broker_and_no_stubs(pg_bin: Path, tmp_path: Path) -> None:
    """user-service's profile asks for neither: nothing more is started for it."""
    with Harness(config(pg_bin, tmp_path), base_env=BASE_ENV, work_root=tmp_path) as harness:
        assert harness.kafka is None
        assert harness.stubs == {}
        assert harness.endpoints.kafka_bootstrap is None
        assert harness.endpoints.service_urls == {}


@needs_kafka_jars
def test_notification_service_gets_a_broker_with_its_topics_and_a_stub_per_called_service(
    pg_bin: Path, tmp_path: Path
) -> None:
    """Its exact env contract, pointing at a live broker holding its four input topics and
    at a stub for user-service and one for order-service; all of it gone afterwards."""
    run = notification_config(pg_bin, tmp_path, CDC_HOME)
    with Harness(run, base_env=BASE_ENV, work_root=tmp_path) as harness:
        with urllib.request.urlopen(f"{harness.base_url}/__env") as response:
            received = json.loads(response.read())
        assert received == service_env("notification-service", harness.endpoints, base_env=BASE_ENV)
        assert harness.kafka is not None
        assert received["KAFKA_BOOTSTRAP_SERVERS"] == harness.kafka.bootstrap
        admin = KafkaAdminClient(bootstrap_servers=harness.kafka.bootstrap)
        try:
            topics = set(admin.list_topics())
        finally:
            admin.close()
        assert {"user-events", "order-events", "payment-events", "fulfilment-events"} <= topics
        assert set(harness.stubs) == {"user-service", "order-service"}
        assert received["USER_SERVICE_URL"] == harness.stubs["user-service"].url
        assert received["ORDER_SERVICE_URL"] == harness.stubs["order-service"].url
        status, body = get(f"{received['USER_SERVICE_URL']}/users/{USER_ID}")
        assert (status, json.loads(body)["userId"]) == (200, USER_ID)
        assert get(f"{received['ORDER_SERVICE_URL']}/orders/{ORDER_ID}") == (404, b"")
        assert [r.path for r in harness.stubs["user-service"].requests()] == [f"/users/{USER_ID}"]
        assert [r.path for r in harness.stubs["order-service"].requests()] == [
            f"/orders/{ORDER_ID}"
        ]
        work_dir = harness.work_dir
        ports = [harness.kafka.port, *(stub.port for stub in harness.stubs.values())]
    assert not work_dir.exists()
    assert processes_mentioning(str(work_dir)) == []
    assert all(port_closed(port) for port in ports)


def test_a_broker_that_cant_start_tears_everything_down(pg_bin: Path, tmp_path: Path) -> None:
    """No Kafka jars: the broker's error propagates; Postgres and the OTLP stub stop."""
    empty = tmp_path / "no-jars"
    empty.mkdir()
    work_root = tmp_path / "runs"
    work_root.mkdir()
    harness = Harness(
        notification_config(pg_bin, tmp_path, empty), base_env=BASE_ENV, work_root=work_root
    )
    with pytest.raises(CdcError, match="no CDC jars"):
        harness.__enter__()
    assert list(work_root.iterdir()) == []
    assert processes_mentioning(str(work_root)) == []
