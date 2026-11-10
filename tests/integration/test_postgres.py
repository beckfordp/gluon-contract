# SPDX-License-Identifier: MIT

"""The throwaway PostgreSQL cluster (RUST-1.2 spec FR3).

The service logs in as the domain user with a password over TCP, exactly as
gluon-local's `<domain>-postgres` deployments are set up.
"""

import socket
import subprocess
from pathlib import Path

import pytest
from processes import processes_mentioning

from gluon_contract.env_contract import postgres_login
from gluon_contract.ports import free_port
from gluon_contract.postgres import PostgresError, ThrowawayPostgres

LOGIN = postgres_login("user-service")


def psql(
    pg_bin: Path, port: int, sql: str, *, password: str = LOGIN.password
) -> subprocess.CompletedProcess[str]:
    """Runs one statement over TCP as the domain user, the way the service connects."""
    return subprocess.run(
        [
            str(pg_bin / "psql"),
            "-X",
            "-tA",
            "-c",
            sql,
            f"host=127.0.0.1 port={port} user={LOGIN.user} dbname={LOGIN.database} "
            f"password={password} connect_timeout=5",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def test_a_started_cluster_accepts_the_domain_login_over_tcp(pg_bin: Path, tmp_path: Path) -> None:
    """The domain user, with its password, over TCP, into the domain database."""
    with ThrowawayPostgres(pg_bin, tmp_path, LOGIN) as pg:
        assert pg.endpoint.host == "127.0.0.1"
        done = psql(pg_bin, pg.endpoint.port, "select current_user || ' ' || current_database()")
        assert done.returncode == 0, done.stderr
        assert done.stdout.strip() == "user user"


def test_a_wrong_password_is_refused(pg_bin: Path, tmp_path: Path) -> None:
    """TCP logins really check the password (scram-sha-256), so a passing login proves something."""
    with ThrowawayPostgres(pg_bin, tmp_path, LOGIN) as pg:
        done = psql(pg_bin, pg.endpoint.port, "select 1", password="not-the-password")
        assert done.returncode != 0
        assert "password authentication failed" in done.stderr


def test_logical_replication_is_enabled(pg_bin: Path, tmp_path: Path) -> None:
    """`wal_level=logical`, which Debezium needs (RUST-1.8; ADR 0008's prerequisites)."""
    with ThrowawayPostgres(pg_bin, tmp_path, LOGIN) as pg:
        assert psql(pg_bin, pg.endpoint.port, "show wal_level").stdout.strip() == "logical"


def test_stop_and_start_keep_the_data(pg_bin: Path, tmp_path: Path) -> None:
    """stop() refuses connections (for readiness checks); start() brings the same data back."""
    with ThrowawayPostgres(pg_bin, tmp_path, LOGIN) as pg:
        port = pg.endpoint.port
        assert (
            psql(
                pg_bin, port, "create table kept (id int); insert into kept values (42)"
            ).returncode
            == 0
        )
        pg.stop()
        assert not pg.running
        assert psql(pg_bin, port, "select 1").returncode != 0
        pg.start()
        assert pg.running
        assert psql(pg_bin, port, "select id from kept").stdout.strip() == "42"


def test_nothing_survives_the_context(pg_bin: Path, tmp_path: Path) -> None:
    """No server process and no data or socket directory after exit."""
    with ThrowawayPostgres(pg_bin, tmp_path, LOGIN) as pg:
        data_dir, socket_dir = pg.data_dir, pg.socket_dir
        assert processes_mentioning(str(data_dir))
    assert not data_dir.exists()
    assert not socket_dir.exists()
    assert processes_mentioning(str(data_dir)) == []


def test_a_failed_start_reports_the_server_log_and_leaves_nothing(
    pg_bin: Path, tmp_path: Path
) -> None:
    """A port already in use: the error carries the server's own reason, and nothing is left."""
    port = free_port()
    with socket.create_server(("127.0.0.1", port)):
        postgres = ThrowawayPostgres(pg_bin, tmp_path, LOGIN, port=port)
        with pytest.raises(PostgresError, match="could not bind"):
            postgres.__enter__()
    assert not postgres.data_dir.exists()
    assert not postgres.socket_dir.exists()
    assert processes_mentioning(str(postgres.data_dir)) == []


def test_keep_leaves_the_data_directory_for_inspection(pg_bin: Path, tmp_path: Path) -> None:
    """With keep=True (CONTRACT_KEEP_ARTIFACTS) the data and log stay; the server still stops."""
    with ThrowawayPostgres(pg_bin, tmp_path, LOGIN, keep=True) as pg:
        data_dir = pg.data_dir
    assert (data_dir / "PG_VERSION").is_file()
    assert pg.log_file.is_file()
    assert processes_mentioning(str(data_dir)) == []


def test_free_ports_are_bindable_and_distinct() -> None:
    """free_port() hands out ports nothing is listening on."""
    ports = {free_port() for _ in range(5)}
    assert len(ports) == 5
    for port in ports:
        with socket.create_server(("127.0.0.1", port)):
            pass


def test_a_failing_initdb_reports_its_output_and_leaves_nothing(tmp_path: Path) -> None:
    """Broken binaries fail with the tool's own message; there is no server log yet."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    initdb = fake_bin / "initdb"
    initdb.write_text("#!/bin/sh\necho 'initdb: cannot be run as root' >&2\nexit 3\n")
    initdb.chmod(0o755)
    postgres = ThrowawayPostgres(fake_bin, tmp_path, LOGIN)
    with pytest.raises(PostgresError) as raised:
        postgres.__enter__()
    message = str(raised.value)
    assert "initdb failed (3): initdb: cannot be run as root" in message
    assert "(no server log)" in message
    assert not postgres.socket_dir.exists()
