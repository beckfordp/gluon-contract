# SPDX-License-Identifier: MIT

"""Seeding `sent_email` with the captured rows (gluon RPN-4 helper)."""

import os
import subprocess
from pathlib import Path

import psycopg
from psycopg import sql

from gluon_contract.capture import capture_file
from gluon_contract.env_contract import postgres_login
from gluon_contract.postgres import ThrowawayPostgres
from gluon_contract.sent_email import COLUMNS, SERVICE, SentEmailRow, captured_rows, insert

LOGIN = postgres_login(SERVICE)


def load_captured_schema(pg_bin: Path, pg: ThrowawayPostgres) -> None:
    """The Scala service's `sent_email`, from the capture's pg_dump (psql: it has meta-commands)."""
    subprocess.run(
        [
            str(pg_bin / "psql"),
            "--no-psqlrc",
            "--quiet",
            "--set=ON_ERROR_STOP=1",
            f"--host={pg.endpoint.host}",
            f"--port={pg.endpoint.port}",
            f"--username={LOGIN.user}",
            f"--dbname={LOGIN.database}",
            f"--file={capture_file('db/schema.sql', service=SERVICE)}",
        ],
        env={**os.environ, "PGPASSWORD": LOGIN.password},
        check=True,
        capture_output=True,
    )


def test_the_captured_rows_go_in_and_come_back_unchanged(pg_bin: Path, tmp_path: Path) -> None:
    """Every column of every row, microseconds and nulls included, into the Scala table."""
    rows = captured_rows()
    with ThrowawayPostgres(pg_bin, tmp_path, LOGIN) as pg:
        load_captured_schema(pg_bin, pg)
        with psycopg.connect(
            host=pg.endpoint.host,
            port=pg.endpoint.port,
            dbname=LOGIN.database,
            user=LOGIN.user,
            password=LOGIN.password,
            autocommit=True,
        ) as connection:
            insert(connection, rows)
            query = sql.SQL("select {} from sent_email").format(
                sql.SQL(", ").join(
                    sql.SQL("id::text") if column == "id" else sql.Identifier(column)
                    for column in COLUMNS
                )
            )
            back = [SentEmailRow(*values) for values in connection.execute(query)]
    assert sorted(back, key=lambda row: row.id) == sorted(rows, key=lambda row: row.id)
