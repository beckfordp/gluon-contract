# SPDX-License-Identifier: MIT

"""Seeding `sent_email` with the captured rows (gluon RPN-4 helper)."""

import os
import subprocess
from pathlib import Path

from gluon_contract.capture import capture_file
from gluon_contract.env_contract import postgres_login
from gluon_contract.postgres import ThrowawayPostgres, connect
from gluon_contract.sent_email import SERVICE, captured_rows, insert, rows

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
    """Every column of every row, microseconds and nulls included, into the Scala table and
    back out through `rows`, oldest first as the capture dumped them."""
    captured = captured_rows()
    with ThrowawayPostgres(pg_bin, tmp_path, LOGIN) as pg:
        load_captured_schema(pg_bin, pg)
        with connect(pg.endpoint) as connection:
            insert(connection, list(reversed(captured)))
            back = rows(connection)
    assert back == captured


def test_rows_reads_one_source_events_rows(pg_bin: Path, tmp_path: Path) -> None:
    """`source_event_id` narrows to that event's rows (RPN-10: the welcome email is one row,
    however often its event is delivered); an event with none has none."""
    captured = captured_rows()
    welcome = "e0000000-0000-4000-8000-000000000001"
    with ThrowawayPostgres(pg_bin, tmp_path, LOGIN) as pg:
        load_captured_schema(pg_bin, pg)
        with connect(pg.endpoint) as connection:
            insert(connection, captured)
            found = rows(connection, source_event_id=welcome)
            none = rows(connection, source_event_id="e0000000-0000-4000-8000-000000000002")
    assert found == [row for row in captured if row.source_event_id == welcome]
    assert len(found) == 1
    assert none == []
