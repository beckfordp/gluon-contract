# SPDX-License-Identifier: MIT

"""Runtime config (gluon PLAN.md RUST-1.7; ADR 0028 "Config" row).

Reference: user-service application.conf (variables and defaults), ADR 0028
("invalid values fail startup as they do in Scala"), purerest Tracing
(service.name = the configured service name). Each check starts its own
instance of the build under test beside the harness's, on the same database
and OTLP stub.
"""

import json
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg
import pytest
from support import new_email, signed_up

from gluon_contract.harness import Harness
from gluon_contract.http import request
from gluon_contract.ports import free_port
from gluon_contract.target import TargetProcess

pytestmark = pytest.mark.service("user-service")
"""user-service's contract: deselected in a run for another service (RPN-3)."""

type Db = psycopg.Connection[tuple[Any, ...]]

# The JVM runtime instrumentations' scopes (capture metrics.txt): fixed names, not the
# service's; the Rust build has none.
JVM_RUNTIME_SCOPES = frozenset({"cats.effect.runtime", "io.opentelemetry.runtime-telemetry-java8"})


@contextmanager
def variant(harness: Harness, tmp_path: Path, **overrides: str) -> Iterator[TargetProcess]:
    """Another instance, its environment the harness's plus `overrides`, on fresh ports."""
    env = dict(harness.target.env)
    env["USER_SERVICE_PORT"] = str(free_port())
    env["USER_SERVICE_METRICS_PORT"] = str(free_port())
    env.update(overrides)
    process = TargetProcess(
        argv=harness.config.target_argv,
        cwd=harness.config.target_cwd,
        env=env,
        log_file=tmp_path / "variant.log",
        readiness_url=f"http://127.0.0.1:{env['USER_SERVICE_PORT']}/health/ready",
        readiness_deadline_s=harness.config.readiness_deadline_s,
    )
    try:
        yield process
    finally:
        process.stop()


def started(process: TargetProcess) -> str:
    """Starts a variant, waits until it is ready, and returns its base URL.

    `variant` stops it on the way out.
    """
    process.start()
    process.wait_until_ready()
    return f"http://127.0.0.1:{process.env['USER_SERVICE_PORT']}"


@pytest.mark.parametrize(
    "override",
    [
        {"USER_SERVICE_PORT": "notaport"},
        {"AUTH_PBKDF2_ITERATIONS": "0"},
        {"AUTH_ACCESS_TOKEN_TTL": "500ms"},
        {"OTEL_TRACES_SAMPLER_ARG": "abc"},
    ],
)
def test_an_invalid_value_stops_startup(
    harness: Harness, tmp_path: Path, override: dict[str, str]
) -> None:
    """The process exits non-zero and never answers.

    Source: ADR 0028 Config row; application.conf (port, auth.iterations, TTLs),
    purerest TracingConfig.fromEnv ("a malformed OTEL_TRACES_SAMPLER_ARG fails startup").
    """
    with variant(harness, tmp_path, **override) as process:
        process.start()
        deadline = time.monotonic() + 60
        while process.returncode is None:
            assert time.monotonic() < deadline, f"still running with {override}"
            time.sleep(0.2)
        assert process.returncode != 0, override


def test_the_pbkdf2_iteration_count_is_configurable(
    harness: Harness, tmp_path: Path, db: Db
) -> None:
    """AUTH_PBKDF2_ITERATIONS sets the count new hashes record.

    Source: application.conf (auth.iterations ← AUTH_PBKDF2_ITERATIONS).
    """
    with variant(harness, tmp_path, AUTH_PBKDF2_ITERATIONS="1000") as process:
        user_id = signed_up(started(process), new_email())["userId"]
    row = db.execute(
        'select password_hash from "user_account" where id = %s', (user_id,)
    ).fetchone()
    assert row is not None
    assert row[0].startswith("pbkdf2$1000$"), row[0]


def test_the_access_token_lifetime_is_configurable(
    harness: Harness, tmp_path: Path, db: Db
) -> None:
    """AUTH_ACCESS_TOKEN_TTL (a HOCON duration) sets access-token expiry.

    Source: application.conf (auth.access-token-ttl ← AUTH_ACCESS_TOKEN_TTL).
    """
    with variant(harness, tmp_path, AUTH_ACCESS_TOKEN_TTL="2h") as process:
        user_id = signed_up(started(process), new_email())["userId"]
    row = db.execute(
        "select extract(epoch from expires_at - created_at) from auth_tokens"
        " where user_id = %s and kind = 'access'",
        (user_id,),
    ).fetchone()
    assert row is not None
    assert abs(float(row[0]) - 7200) <= 10, row


def test_the_service_name_names_the_spans(harness: Harness, tmp_path: Path) -> None:
    """USER_SERVICE_NAME becomes service.name.

    Source: application.conf (service-name ← USER_SERVICE_NAME); purerest Tracing
    ("Spans carry service.name = serviceName").
    """
    with variant(harness, tmp_path, USER_SERVICE_NAME="renamed-user-service") as process:
        signed_up(started(process), new_email())
        harness.otlp.wait_for_spans(
            lambda s: s.service_name == "renamed-user-service", timeout_s=20
        )


def test_the_service_name_names_the_logger(harness: Harness, tmp_path: Path) -> None:
    """USER_SERVICE_NAME is the logger_name of the service's own lines.

    Source: purerest Logging.create (Slf4jLogger.fromName(serviceName)); capture
    stdout.log (logger_name "user-service"). Implicit behaviour (RUST-1.9).
    """
    with variant(harness, tmp_path, USER_SERVICE_NAME="renamed-user-service") as process:
        signed_up(started(process), new_email())
        line = process.wait_for_log(lambda text: '"Account created"' in text, timeout_s=20)
    assert json.loads(line)["logger_name"] == "renamed-user-service"


def test_the_event_source_stays_user_service(harness: Harness, tmp_path: Path, db: Db) -> None:
    """USER_SERVICE_NAME doesn't reach the envelope: source is always "user-service".

    Source: user-service AuthEvents (eventSource = "user-service", a constant);
    docs/system-design.md "Envelope" (the publishing service's name). Implicit
    behaviour (RUST-1.9).
    """
    with variant(harness, tmp_path, USER_SERVICE_NAME="renamed-user-service") as process:
        user_id = signed_up(started(process), new_email())["userId"]
    row = db.execute(
        "select payload->>'source' from outbox_events where aggregate_id = %s", (user_id,)
    ).fetchone()
    assert row == ("user-service",)


def test_the_service_name_scopes_the_metrics(harness: Harness, tmp_path: Path) -> None:
    """USER_SERVICE_NAME is the otel_scope_name of every service series (the JVM runtime
    scopes aside).

    Source: purerest Metrics.oteljava (meterProvider.get(instrumentationName =
    serviceName)); capture metrics.txt (otel_scope_name="user-service", beside
    "cats.effect.runtime" and "io.opentelemetry.runtime-telemetry-java8"). Implicit
    behaviour (RUST-1.9).
    """
    with variant(harness, tmp_path, USER_SERVICE_NAME="renamed-user-service") as process:
        base_url = started(process)
        request(base_url, "GET", "/health")
        port = process.env["USER_SERVICE_METRICS_PORT"]
        scrape = request(f"http://127.0.0.1:{port}", "GET", "/metrics").text
    scopes = set(re.findall(r'otel_scope_name="([^"]*)"', scrape))
    assert scopes - JVM_RUNTIME_SCOPES == {"renamed-user-service"}, scopes
