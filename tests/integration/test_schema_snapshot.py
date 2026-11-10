# SPDX-License-Identifier: MIT

"""Snapshotting a live schema (RUST-1.5 helper)."""

from pathlib import Path

import psycopg

from gluon_contract.env_contract import postgres_login
from gluon_contract.postgres import ThrowawayPostgres
from gluon_contract.schema import create_reference, diff_snapshots, snapshot

LOGIN = postgres_login("user-service")
SQL = """
create table "user_account" (id uuid primary key, email text not null unique);
create table flyway_schema_history (installed_rank int primary key);
create index user_account_email_idx on "user_account" (email);
"""


def connect(pg: ThrowawayPostgres, database: str) -> psycopg.Connection[tuple[object, ...]]:
    """The domain user's connection to `database`."""
    return psycopg.connect(
        host=pg.endpoint.host,
        port=pg.endpoint.port,
        dbname=database,
        user=LOGIN.user,
        password=LOGIN.password,
        autocommit=True,
    )


def test_the_same_sql_gives_the_same_snapshot_and_history_tables_are_ignored(
    pg_bin: Path, tmp_path: Path
) -> None:
    """Two databases built from one script match; migration history doesn't count."""
    with ThrowawayPostgres(pg_bin, tmp_path, LOGIN) as pg:
        (tmp_path / "V1__schema.sql").write_text(SQL)
        with (
            connect(pg, LOGIN.database) as service,
            create_reference(service, [tmp_path / "V1__schema.sql"]) as reference,
        ):
            service.execute(SQL)
            assert diff_snapshots(snapshot(reference), snapshot(service)) == []
            assert "flyway_schema_history" not in snapshot(service)["tables"]


def test_a_different_schema_is_reported(pg_bin: Path, tmp_path: Path) -> None:
    """A changed column type and a missing index both show up."""
    with ThrowawayPostgres(pg_bin, tmp_path, LOGIN) as pg:
        (tmp_path / "V1__schema.sql").write_text(SQL)
        with (
            connect(pg, LOGIN.database) as service,
            create_reference(service, [tmp_path / "V1__schema.sql"]) as reference,
        ):
            service.execute(
                'create table "user_account"'
                " (id uuid primary key, email varchar(200) not null unique)"
            )
            differences = diff_snapshots(snapshot(reference), snapshot(service))
            assert any("column user_account.email" in d for d in differences)
            assert any("index user_account_email_idx" in d and "missing" in d for d in differences)
