# SPDX-License-Identifier: MIT

"""A throwaway PostgreSQL 16 cluster from the local binaries (RUST-1.2 spec FR3).

Set up like gluon-local's `<domain>-postgres` deployments: the domain user is
the superuser and logs in over TCP with a scram-sha-256 password, into the
domain database. `wal_level=logical` is on for the CDC stack (RUST-1.8). Only
the cluster's private Unix socket trusts local connections, for setting up.
"""

import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Self

from gluon_contract.env_contract import PostgresLogin
from gluon_contract.ports import free_port

HOST = "127.0.0.1"
START_TIMEOUT_S = 30
LOG_TAIL_LINES = 20


class PostgresError(Exception):
    """The cluster couldn't be created, started or stopped."""


@dataclass(frozen=True, slots=True)
class PostgresEndpoint:
    """How the service under test reaches its database."""

    host: str
    port: int
    login: PostgresLogin


class ThrowawayPostgres:
    """A PostgreSQL cluster that exists for one run.

    Use as a context manager: entering creates and starts the cluster and the
    domain database; leaving stops it and removes its directories (unless
    `keep`). A failure while entering cleans up before raising.
    """

    def __init__(
        self,
        pg_bin: Path,
        work_dir: Path,
        login: PostgresLogin,
        *,
        port: int | None = None,
        keep: bool = False,
    ) -> None:
        """Prepares, but doesn't start, a cluster under `work_dir`.

        Args:
            pg_bin: the directory holding initdb, pg_ctl and createdb.
            work_dir: where the data directory and server log go.
            login: the database and credentials the service expects.
            port: the TCP port; a free one by default.
            keep: leave the data directory and log behind for inspection.
        """
        self._pg_bin = pg_bin
        self._login = login
        self._keep = keep
        self.data_dir = work_dir / "postgres-data"
        self.log_file = work_dir / "postgres.log"
        # Unix socket paths are limited to ~107 bytes, so not under work_dir.
        self.socket_dir = Path(tempfile.mkdtemp(prefix="gc-pg-"))
        self.endpoint = PostgresEndpoint(HOST, port if port is not None else free_port(), login)
        self.running = False

    def __enter__(self) -> Self:
        """Creates the cluster, starts it and creates the domain database."""
        try:
            self._initdb()
            self.start()
            self._tool(
                "createdb",
                "-h",
                str(self.socket_dir),
                "-p",
                str(self.endpoint.port),
                "-U",
                self._login.user,
                self._login.database,
            )
        except BaseException:
            self._tear_down()
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Stops the server and removes its directories."""
        self._tear_down()

    def start(self) -> None:
        """Starts the server and waits until it accepts connections."""
        options = " ".join(
            [
                f"-c listen_addresses={HOST}",
                f"-c port={self.endpoint.port}",
                f"-c unix_socket_directories={self.socket_dir}",
                "-c wal_level=logical",
            ]
        )
        self._tool(
            "pg_ctl",
            "start",
            "-D",
            str(self.data_dir),
            "-l",
            str(self.log_file),
            "-w",
            "-t",
            str(START_TIMEOUT_S),
            "-o",
            options,
        )
        self.running = True

    def stop(self) -> None:
        """Stops the server (fast shutdown); the data stays for a later `start`.

        Also acts when `running` is False but a postmaster.pid exists: a start
        that timed out can leave a server coming up that must not outlive the run.
        """
        if self.running or (self.data_dir / "postmaster.pid").exists():
            self._tool("pg_ctl", "stop", "-D", str(self.data_dir), "-m", "fast", "-w")
            self.running = False

    def log_tail(self) -> str:
        """The last lines of the server log, for error messages."""
        try:
            lines = self.log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return "(no server log)"
        return "\n".join(lines[-LOG_TAIL_LINES:])

    def _initdb(self) -> None:
        password_file = self.socket_dir / "password"
        password_file.write_text(self._login.password + "\n", encoding="utf-8")
        try:
            self._tool(
                "initdb",
                "-D",
                str(self.data_dir),
                "-U",
                self._login.user,
                f"--pwfile={password_file}",
                "--auth-local=trust",
                "--auth-host=scram-sha-256",
                "--encoding=UTF8",
                "--locale=C.UTF-8",
            )
        finally:
            password_file.unlink(missing_ok=True)

    def _tool(self, tool: str, *args: str) -> None:
        argv: Sequence[str] = [str(self._pg_bin / tool), *args]
        done = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=120)
        if done.returncode != 0:
            raise PostgresError(
                f"{tool} failed ({done.returncode}): {done.stderr.strip() or done.stdout.strip()}\n"
                f"--- server log ({self.log_file}) ---\n{self.log_tail()}"
            )

    def _tear_down(self) -> None:
        try:
            self.stop()
        finally:
            shutil.rmtree(self.socket_dir, ignore_errors=True)
            if not self._keep:
                shutil.rmtree(self.data_dir, ignore_errors=True)
