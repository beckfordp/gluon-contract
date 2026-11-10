# SPDX-License-Identifier: MIT

"""Schema snapshots and their differences (RUST-1.5).

The reference schema is the Scala service's migration files applied to an
empty database (ADR 0028 decision 5). A snapshot holds what the contract
cares about in the `public` schema: tables, columns, constraints and indexes.
Migration history tables are implementation details and are left out.
"""

import re
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TypedDict

import psycopg
from psycopg import sql

HISTORY_TABLES = ("flyway_schema_history", "_sqlx_migrations")
"""Each implementation's migration bookkeeping; not part of the contract."""

MIGRATION = re.compile(r"^V(\d+)__.*\.sql$")


class Snapshot(TypedDict):
    """What the contract cares about in the `public` schema."""

    tables: set[str]
    columns: dict[tuple[str, str], tuple[str, str, str | None]]
    """(table, column) → (data type, nullable, default)."""
    constraints: dict[tuple[str, str], tuple[str, str]]
    """(table, name) → (kind, definition)."""
    indexes: dict[str, str]
    """name → definition."""


type Connection = psycopg.Connection[tuple[Any, ...]]


def snapshot(connection: Connection) -> Snapshot:
    """The `public` schema of the connected database."""
    history = list(HISTORY_TABLES)
    tables = {
        row[0]
        for row in connection.execute(
            "select table_name from information_schema.tables where table_schema = 'public'"
            " and table_type = 'BASE TABLE' and table_name <> all(%s)",
            (history,),
        )
    }
    columns = {
        (row[0], row[1]): (row[2], row[3], row[4])
        for row in connection.execute(
            "select table_name, column_name, data_type, is_nullable, column_default"
            " from information_schema.columns where table_schema = 'public'"
            " and table_name <> all(%s)",
            (history,),
        )
    }
    constraints = {
        (row[0], row[1]): (row[2], row[3])
        for row in connection.execute(
            "select rel.relname, con.conname, con.contype::text, pg_get_constraintdef(con.oid)"
            " from pg_constraint con join pg_class rel on rel.oid = con.conrelid"
            " join pg_namespace ns on ns.oid = rel.relnamespace"
            " where ns.nspname = 'public' and rel.relname <> all(%s)",
            (history,),
        )
    }
    indexes = {
        row[0]: row[1]
        for row in connection.execute(
            "select indexname, indexdef from pg_indexes where schemaname = 'public'"
            " and tablename <> all(%s)",
            (history,),
        )
    }
    return Snapshot(tables=tables, columns=columns, constraints=constraints, indexes=indexes)


def diff_snapshots(expected: Snapshot, actual: Snapshot) -> list[str]:
    """Every difference, one line each: missing, unexpected, or changed."""
    differences: list[str] = []

    def compare(kind: str, want: dict[Any, Any], got: dict[Any, Any]) -> None:
        for key in sorted(set(want) | set(got), key=str):
            label = ".".join(key) if isinstance(key, tuple) else key
            if key not in got:
                differences.append(f"{kind} {label}: missing (expected {want[key]})")
            elif key not in want:
                differences.append(f"{kind} {label}: unexpected ({got[key]})")
            elif want[key] != got[key]:
                differences.append(f"{kind} {label}: expected {want[key]}, got {got[key]}")

    compare(
        "table",
        dict.fromkeys(expected["tables"], "table"),
        dict.fromkeys(actual["tables"], "table"),
    )
    compare("column", expected["columns"], actual["columns"])
    compare("constraint", expected["constraints"], actual["constraints"])
    compare("index", expected["indexes"], actual["indexes"])
    return differences


def migration_files(directory: Path) -> list[Path]:
    """`V<n>__*.sql` files in version order."""
    versioned = [
        (int(match.group(1)), path)
        for path in directory.iterdir()
        if (match := MIGRATION.match(path.name)) is not None
    ]
    return [path for _, path in sorted(versioned)]


@contextmanager
def create_reference(connection: Connection, sql_files: Sequence[Path]) -> Iterator[Connection]:
    """A fresh database in the same cluster with `sql_files` applied; dropped afterwards.

    `connection` must be able to create databases (the domain user is the
    throwaway cluster's superuser).
    """
    name = f"reference_{uuid.uuid4().hex[:12]}"
    info = connection.info
    connection.execute(sql.SQL("create database {}").format(sql.Identifier(name)))
    try:
        with psycopg.connect(
            host=info.host,
            port=info.port,
            dbname=name,
            user=info.user,
            password=info.password,
            autocommit=True,
        ) as reference:
            for path in sql_files:
                reference.execute(path.read_text(encoding="utf-8").encode())
            yield reference
    finally:
        connection.execute(
            sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(name))
        )
