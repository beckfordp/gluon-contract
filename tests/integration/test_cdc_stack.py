# SPDX-License-Identifier: MIT

"""The sandbox CDC stack end to end (RUST-1.8): Postgres → Debezium → Kafka.

Needs the jars `bin/sandbox-setup --only cdc` installs (or CONTRACT_CDC_HOME);
skipped, visibly, without them.
"""

import json
import os
import subprocess
import time
import uuid
from pathlib import Path

import pytest

from gluon_contract.cdc import CdcStack, cdc_home
from gluon_contract.env_contract import postgres_login
from gluon_contract.kafka import Record
from gluon_contract.postgres import ThrowawayPostgres

LOGIN = postgres_login("user-service")
SWITCH_RESET = Path(__file__).resolve().parents[4] / "infra/k8s/local-infra/user-switch-reset.sql"
"""What gluon bin/k8s-local-up runs on the user database when it switches implementation."""
MIGRATION = """
CREATE TABLE _sqlx_migrations (version BIGINT PRIMARY KEY, description TEXT NOT NULL);
INSERT INTO _sqlx_migrations VALUES (1, 'outbox');
"""
"""A new service's migration history: rows written before the connector restarts."""
HOME = cdc_home(os.environ)
OUTBOX = """
CREATE TABLE outbox_events (
    id UUID PRIMARY KEY,
    aggregate_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    trace_parent TEXT,
    correlation_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

pytestmark = pytest.mark.skipif(
    not (HOME / "COMPLETE").is_file(),
    reason=f"no CDC jars in {HOME} (bin/sandbox-setup --only cdc)",
)


def psql(pg_bin: Path, pg: ThrowawayPostgres, sql: str, *, flag: str = "-c") -> None:
    """Runs SQL (`-c`), or a file of it (`flag="-f"`), as the domain user over the
    cluster's socket, stopping at the first error."""
    subprocess.run(
        [
            str(pg_bin / "psql"),
            "-X",
            "-q",
            "-v",
            "ON_ERROR_STOP=1",
            "-h",
            str(pg.socket_dir),
            "-p",
            str(pg.endpoint.port),
            "-U",
            LOGIN.user,
            "-d",
            LOGIN.database,
            flag,
            sql,
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )


def publish(pg_bin: Path, pg: ThrowawayPostgres, cdc: CdcStack) -> Record:
    """Inserts an outbox row and waits for it on `user-events`."""
    user_id = str(uuid.uuid4())
    psql(
        pg_bin,
        pg,
        "INSERT INTO outbox_events (id, aggregate_id, payload, correlation_id)"
        f" VALUES ('{uuid.uuid4()}', '{user_id}', '{{}}', '{user_id}')",
    )
    return cdc.record("user-events", lambda r: r.key == user_id, timeout_s=90)


def wait_for_offset(offsets: Path, after: float) -> None:
    """Until the worker has written its offsets file since `after` (it flushes every
    second), so a restart resumes from the slot rather than snapshotting afresh."""
    deadline = time.monotonic() + 10
    while not (offsets.is_file() and offsets.stat().st_mtime > after):
        assert time.monotonic() < deadline, f"no offset committed to {offsets}"
        time.sleep(0.25)


def test_an_outbox_row_arrives_on_its_topic_as_routed(pg_bin: Path, tmp_path: Path) -> None:
    """Key, value and headers exactly as the registered connector routes them."""
    with ThrowawayPostgres(pg_bin, tmp_path, LOGIN) as pg:
        psql(pg_bin, pg, OUTBOX)
        with CdcStack(HOME, tmp_path / "cdc", pg.endpoint) as cdc:
            row_id, user_id = uuid.uuid4(), str(uuid.uuid4())
            payload = {"eventType": "UserRegistered", "correlationId": user_id}
            psql(
                pg_bin,
                pg,
                "INSERT INTO outbox_events"
                " (id, aggregate_id, payload, trace_parent, correlation_id)"
                f" VALUES ('{row_id}', '{user_id}', '{json.dumps(payload)}',"
                f" '00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01', '{user_id}')",
            )
            record = cdc.record("user-events", lambda r: r.key == user_id, timeout_s=60)
    assert record.value is not None
    assert json.loads(record.value) == payload
    assert record.headers == {
        "id": str(row_id),
        "traceparent": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01",
        "correlation_id": user_id,
    }


def test_after_a_schema_reset_and_a_connector_restart_rows_flow_again(
    pg_bin: Path, tmp_path: Path
) -> None:
    """The implementation switch's sequence (ADR 0028 decision 7; gluon bin/k8s-local-up),
    after the old service has published and the connector committed its offset: run the
    reset file, let the new service migrate (outbox_events again, and its migration
    history, written before the restart), restart the connector: the new table's rows
    are published.
    """
    with ThrowawayPostgres(pg_bin, tmp_path, LOGIN) as pg:
        psql(pg_bin, pg, OUTBOX)
        with CdcStack(HOME, tmp_path / "cdc", pg.endpoint) as cdc:
            committed_after = time.time()
            publish(pg_bin, pg, cdc)
            wait_for_offset(tmp_path / "cdc" / "connect.offsets", committed_after)
            psql(pg_bin, pg, str(SWITCH_RESET), flag="-f")
            psql(pg_bin, pg, OUTBOX + MIGRATION)
            cdc.restart_connector()
            record = publish(pg_bin, pg, cdc)
    assert record.value == "{}"
