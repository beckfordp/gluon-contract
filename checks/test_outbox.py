# SPDX-License-Identifier: MIT

"""The outbox row and the Kafka envelope (gluon PLAN.md RUST-1.6; ADR 0028
"Outbox and envelope" row).

Reference: ADR 0008 (outbox + Debezium), ADR 0009 and docs/system-design.md
(envelope; correlationId is the userId on user-events), registry/user-service
(payload schema), the registered connector config, capture
db-outbox-events.jsonl. Never the implementation under test.
"""

import json
import re
from datetime import timedelta
from typing import Any

import psycopg
from support import new_email, post_credentials, signed_up

from gluon_contract.formats import is_uuid, parse_traceparent
from gluon_contract.harness import Harness
from gluon_contract.registry import latest_schema, validation_errors
from gluon_contract.routing import load_connector, route

type Db = psycopg.Connection[tuple[Any, ...]]
JAVA_INSTANT = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d{3}|\.\d{6}|\.\d{9})?Z$")


def outbox_rows(db: Db, user_id: str) -> list[dict[str, Any]]:
    """The user's outbox rows, payload as Postgres renders the JSONB text (as Debezium reads it)."""
    cursor = db.execute(
        "select id::text, aggregate_id, payload::text as payload, trace_parent, correlation_id,"
        " created_at from outbox_events where aggregate_id = %s",
        (user_id,),
    )
    names = [column.name for column in cursor.description or []]
    return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


def test_a_signup_writes_one_outbox_row_keyed_by_the_user(harness: Harness, db: Db) -> None:
    """One row; aggregate_id and correlation_id are the userId.

    Source: ADR 0008; docs/system-design.md (correlationId = userId for user-events);
    capture db-outbox-events.jsonl.
    """
    user_id = signed_up(harness, new_email())["userId"]
    rows = outbox_rows(db, user_id)
    assert len(rows) == 1, rows
    assert rows[0]["aggregate_id"] == rows[0]["correlation_id"] == user_id


def test_a_refused_signup_writes_nothing(harness: Harness, db: Db) -> None:
    """A duplicate (409) or invalid (400) signup adds no outbox row.

    Source: ADR 0008 (the event is written with the state change, or not at all).
    """
    email = new_email()
    signed_up(harness, email)
    before = db.execute("select count(*) from outbox_events").fetchone()
    assert post_credentials(harness, "/auth/signup", email).status == 409
    assert post_credentials(harness, "/auth/signup", "not-an-email").status == 400
    assert db.execute("select count(*) from outbox_events").fetchone() == before


def test_the_envelope_is_the_shared_one_with_user_registered_inside(
    harness: Harness, db: Db
) -> None:
    """eventId (a UUID, not the row id), eventType, timestamp, source, correlationId, payload.

    Source: ADR 0009; docs/system-design.md "Envelope" and "UserRegistered";
    capture db-outbox-events.jsonl (timestamp as Java prints an instant).
    """
    email = new_email()
    user_id = signed_up(harness, email)["userId"]
    (row,) = outbox_rows(db, user_id)
    envelope = json.loads(row["payload"])
    assert set(envelope) == {
        "eventId",
        "eventType",
        "timestamp",
        "source",
        "correlationId",
        "payload",
    }
    assert is_uuid(envelope["eventId"])
    assert envelope["eventId"] != row["id"]
    assert envelope["eventType"] == "UserRegistered"
    assert envelope["source"] == "user-service"
    assert envelope["correlationId"] == user_id
    assert envelope["payload"] == {"userId": user_id, "email": email}
    assert JAVA_INSTANT.match(envelope["timestamp"]), envelope["timestamp"]
    created = db.execute(
        'select created_at from "user_account" where id = %s', (user_id,)
    ).fetchone()
    assert created is not None
    stamped = db.execute("select %s::timestamptz", (envelope["timestamp"],)).fetchone()
    assert stamped is not None
    assert abs(stamped[0] - created[0]) < timedelta(seconds=10)


def test_the_payload_matches_the_registered_schema(harness: Harness, db: Db) -> None:
    """The payload validates against the latest registered version (closed schema).

    Source: registry/user-service/registry.json, user-events-UserRegistered (ADR 0003).
    """
    user_id = signed_up(harness, new_email())["userId"]
    (row,) = outbox_rows(db, user_id)
    schema = latest_schema("user-service", "user-events-UserRegistered")
    assert validation_errors(json.loads(row["payload"])["payload"], schema) == []


def test_debezium_routes_the_row_as_registered(harness: Harness, db: Db) -> None:
    """Topic user-events, key the userId, value the envelope, traceparent and correlation_id.

    Source: infra/k8s/local-infra/debezium-connectors-register.yaml (user-outbox-connector);
    ADR 0008 amendment 2026-11-05 (trace_parent → traceparent header).
    """
    user_id = signed_up(harness, new_email())["userId"]
    (row,) = outbox_rows(db, user_id)
    record = route(row, load_connector("user-outbox-connector.json"))
    assert (record.topic, record.key) == ("user-events", user_id)
    assert json.loads(record.value)["correlationId"] == user_id
    assert record.headers["correlation_id"] == user_id
    traceparent = parse_traceparent(record.headers.get("traceparent") or "")
    assert traceparent is not None, record.headers
    assert traceparent.sampled
