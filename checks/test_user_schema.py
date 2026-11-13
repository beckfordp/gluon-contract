# SPDX-License-Identifier: MIT

"""Schema and stored formats of user-service (gluon PLAN.md RUST-1.5; ADR 0028
decision 5, "Schema and stored formats" row).

Reference: the Scala service's migration files on an empty database, the
capture's stored rows (`db-user-account.txt`, `db-auth-tokens.txt`) and ADR
0028 decision 5. Never the implementation under test.
"""

import os
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

import psycopg
import pytest

from gluon_contract.contracts import CONTRACTS_ROOT, latest_capture
from gluon_contract.formats import PBKDF2_STORED, pbkdf2_matches, sha256_hex
from gluon_contract.harness import Harness
from gluon_contract.http import json_body, request
from gluon_contract.schema import create_reference, diff_snapshots, migration_files, snapshot

pytestmark = pytest.mark.service("user-service")
"""user-service's contract: deselected in a run for another service (RPN-3)."""

PASSWORD = "correct-horse-battery-1"
"""The password CAPTURE.md signs up with; it produced the capture's hashes."""
SCALA_MIGRATIONS = (
    Path(__file__).resolve().parents[3] / "services/user-service/src/main/resources/db/migration"
)
JSON = {"Content-Type": "application/json"}

type Db = psycopg.Connection[tuple[Any, ...]]


def new_email() -> str:
    """A throwaway address."""
    return f"contract-{uuid.uuid4().hex[:12]}@example.com"


def post(harness: Harness, path: str, email: str, password: str = PASSWORD) -> dict[str, Any]:
    """POST a credentials body; return the JSON answer."""
    body = json_body({"email": email, "password": password})
    response = request(harness.base_url, "POST", path, body=body, headers=JSON)
    assert response.status in (200, 201), f"{path}: {response.status} {response.text[:200]}"
    result: dict[str, Any] = response.json()
    return result


def test_the_schema_matches_the_scala_migrations(db: Db) -> None:
    """Same tables, columns, types, nullability, defaults, constraints and indexes,
    migration history tables aside.

    Source: ADR 0028 decision 5; services/user-service/src/main/resources/db/migration/V*.sql.
    """
    directory = Path(os.environ.get("CONTRACT_REFERENCE_MIGRATIONS", SCALA_MIGRATIONS))
    files = migration_files(directory)
    assert [path.name for path in files][:2] == [
        "V1__create_user_table.sql",
        "V2__create_outbox_events.sql",
    ], files
    with create_reference(db, files) as reference:
        assert diff_snapshots(snapshot(reference), snapshot(db)) == []


def test_passwords_are_stored_as_pbkdf2_that_verifies_independently(
    harness: Harness, db: Db
) -> None:
    """`pbkdf2$210000$<16-byte salt>$<32-byte hash>`, base64url: PBKDF2-HMAC-SHA256
    of the UTF-8 password.

    Source: ADR 0028 decision 5; capture db-user-account.txt (the same shape).
    """
    email = new_email()
    user_id = post(harness, "/auth/signup", email)["userId"]
    row = db.execute(
        'select password_hash from "user_account" where id = %s', (user_id,)
    ).fetchone()
    assert row is not None
    match = PBKDF2_STORED.match(row[0])
    assert match is not None, row[0]
    assert match["iterations"] == "210000"
    assert pbkdf2_matches(PASSWORD, row[0])


def test_a_password_hashed_by_the_scala_service_logs_in(harness: Harness, db: Db) -> None:
    """Users created by either implementation can log in to the other.

    Source: ADR 0028 decision 5; capture db-user-account.txt (a Scala-made hash for
    CAPTURE.md's password).
    """
    scala_hash = (
        (latest_capture(CONTRACTS_ROOT, "user-service") / "db-user-account.txt")
        .read_text()
        .splitlines()[0]
    )
    stored = scala_hash.split("|", 1)[1]
    email = new_email()
    user_id = str(uuid.uuid4())
    db.execute(
        'insert into "user_account" (id, email, password_hash) values (%s, %s, %s)',
        (user_id, email, stored),
    )
    assert post(harness, "/auth/login", email)["userId"] == user_id


def test_tokens_are_stored_only_as_sha256_hex(harness: Harness, db: Db) -> None:
    """Signup stores one access token, login an access and a refresh token; only hashes.

    Source: ADR 0028 decision 5; capture db-auth-tokens.txt (kinds, 64-character hashes).
    """
    email = new_email()
    signed_up = post(harness, "/auth/signup", email)
    logged_in = post(harness, "/auth/login", email)
    rows = db.execute(
        'select kind, token_hash from "auth_tokens" where user_id = %s order by created_at, kind',
        (signed_up["userId"],),
    ).fetchall()
    expected = [
        ("access", sha256_hex(signed_up["token"])),
        ("access", sha256_hex(logged_in["token"])),
        ("refresh", sha256_hex(logged_in["refreshToken"])),
    ]
    assert sorted(rows) == sorted(expected)


def test_tokens_live_one_hour_and_thirty_days(harness: Harness, db: Db) -> None:
    """Access tokens expire 1 h, refresh tokens 30 d after they are stored (within 10 s).

    Source: capture db-auth-tokens.txt (00:59:59.97 and 29 days 23:59:59.99);
    application.conf defaults (AUTH_ACCESS_TOKEN_TTL 1h, AUTH_REFRESH_TOKEN_TTL 30d).
    """
    email = new_email()
    user_id = post(harness, "/auth/signup", email)["userId"]
    post(harness, "/auth/login", email)
    lifetimes = db.execute(
        'select kind, expires_at - created_at from "auth_tokens" where user_id = %s',
        (user_id,),
    ).fetchall()
    ttl = {"access": timedelta(hours=1), "refresh": timedelta(days=30)}
    assert {kind for kind, _ in lifetimes} == {"access", "refresh"}
    for kind, lifetime in lifetimes:
        assert ttl[kind] - timedelta(seconds=10) <= lifetime <= ttl[kind], (kind, lifetime)


def test_no_plaintext_password_is_stored_anywhere(harness: Harness, db: Db) -> None:
    """The password appears in no text or JSON column of any table.

    Source: ADR 0028 decision 5 (only the PBKDF2 hash is kept); product-guidelines
    ("Passwords are never stored").
    """
    password = f"plaintext-{uuid.uuid4().hex}"
    post(harness, "/auth/signup", new_email(), password)
    columns = db.execute(
        "select table_name, column_name from information_schema.columns"
        " where table_schema = 'public'"
        " and data_type in ('text', 'character varying', 'jsonb', 'json')"
    ).fetchall()
    for table, column in columns:
        found = db.execute(
            psycopg.sql.SQL("select count(*) from {} where {}::text like %s").format(
                psycopg.sql.Identifier(table), psycopg.sql.Identifier(column)
            ),
            (f"%{password}%",),
        ).fetchone()
        assert found == (0,), f"{table}.{column} holds the plaintext password"
