# SPDX-License-Identifier: MIT

"""The sandbox CDC stack end to end (RUST-1.8): Postgres → Debezium → Kafka.

Needs the jars `bin/sandbox-setup --only cdc` installs (or CONTRACT_CDC_HOME);
skipped, visibly, without them.
"""

import json
import os
import subprocess
import uuid
from pathlib import Path

import pytest

from gluon_contract.cdc import CdcStack, cdc_home
from gluon_contract.env_contract import postgres_login
from gluon_contract.postgres import ThrowawayPostgres

LOGIN = postgres_login("user-service")
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


def psql(pg_bin: Path, pg: ThrowawayPostgres, sql: str) -> None:
    """Runs SQL as the domain user over the cluster's socket."""
    subprocess.run(
        [
            str(pg_bin / "psql"),
            "-X",
            "-q",
            "-h",
            str(pg.socket_dir),
            "-p",
            str(pg.endpoint.port),
            "-U",
            LOGIN.user,
            "-d",
            LOGIN.database,
            "-c",
            sql,
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )


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
    """The implementation switch's sequence (ADR 0028 decision 7; gluon bin/k8s-local-up):
    drop and recreate the public schema and Debezium's publication, let the new service
    create outbox_events again, restart the connector: the new table's rows are published.
    """
    with ThrowawayPostgres(pg_bin, tmp_path, LOGIN) as pg:
        psql(pg_bin, pg, OUTBOX)
        with CdcStack(HOME, tmp_path / "cdc", pg.endpoint) as cdc:
            psql(
                pg_bin,
                pg,
                "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
                " DROP PUBLICATION IF EXISTS dbz_publication;",
            )
            psql(pg_bin, pg, OUTBOX)
            cdc.restart_connector()
            user_id = str(uuid.uuid4())
            psql(
                pg_bin,
                pg,
                "INSERT INTO outbox_events (id, aggregate_id, payload, correlation_id)"
                f" VALUES ('{uuid.uuid4()}', '{user_id}', '{{}}', '{user_id}')",
            )
            record = cdc.record("user-events", lambda r: r.key == user_id, timeout_s=90)
    assert record.value == "{}"
