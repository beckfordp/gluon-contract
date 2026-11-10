# SPDX-License-Identifier: MIT

"""The routed record, for real (gluon PLAN.md RUST-1.8; ADR 0028 "Outbox and envelope"
row: "the routed record (topic, key, traceparent and correlation_id headers)").

Reference: the connector gluon-local registers
(infra/k8s/local-infra/debezium-connectors-register.yaml, user-outbox-connector),
run by Debezium 3.0.0.Final on Kafka Connect 3.8.0 with gluon-local's
StringConverters (the sandbox CDC stack, `cdc` fixture); ADR 0008 and its
2026-11-05 amendment (trace_parent → traceparent header).
"""

import json
from typing import Any

import psycopg
import pytest
from support import new_email, new_traceparent, signed_up

from gluon_contract.cdc import CdcStack, Record
from gluon_contract.formats import is_uuid, parse_traceparent
from gluon_contract.harness import Harness
from gluon_contract.pytest_plugin import TopicReader
from gluon_contract.routing import load_connector, route

type Db = psycopg.Connection[tuple[Any, ...]]


def published(harness: Harness, db: Db, cdc: CdcStack) -> tuple[dict[str, Any], Record]:
    """A traced signup's outbox row and the record Debezium published for it."""
    user_id = signed_up(harness, new_email(), traceparent=new_traceparent())["userId"]
    cursor = db.execute(
        "select id::text as id, aggregate_id, payload::text as payload, trace_parent,"
        " correlation_id from outbox_events where aggregate_id = %s",
        (user_id,),
    )
    names = [column.name for column in cursor.description or []]
    found = cursor.fetchone()
    assert found is not None
    row = dict(zip(names, found, strict=True))
    record = cdc.record("user-events", lambda r: r.key == user_id, timeout_s=60)
    return row, record


def test_a_signup_is_published_on_user_events_as_registered(
    harness: Harness, db: Db, cdc: CdcStack
) -> None:
    """Key the userId; value the payload column's text; headers id, traceparent, correlation_id.

    Source: debezium-connectors-register.yaml (user-outbox-connector: topic replacement
    user-events, key aggregate_id, payload unexpanded, trace_parent:header:traceparent and
    correlation_id:header; EventRouter's default id header); kafka-connect.yaml
    (StringConverter); ADR 0008.
    """
    row, record = published(harness, db, cdc)
    assert (record.topic, record.key) == ("user-events", row["aggregate_id"])
    assert record.value == row["payload"]
    assert record.value is not None
    assert json.loads(record.value)["eventType"] == "UserRegistered"
    assert record.headers == {
        "id": row["id"],
        "traceparent": row["trace_parent"],
        "correlation_id": row["correlation_id"],
    }


def test_the_outbox_groups_stand_in_routes_as_debezium_does(
    harness: Harness, db: Db, cdc: CdcStack
) -> None:
    """routing.route (what the outbox group checks against) gives exactly the real record.

    Source: debezium-connectors-register.yaml (user-outbox-connector) as Debezium 3.0.0
    runs it; gluon_contract.routing is the stand-in the outbox group uses
    where no CDC stack runs.
    """
    row, record = published(harness, db, cdc)
    emulated = route(row, load_connector("user-outbox-connector.json"))
    assert (emulated.topic, emulated.key, emulated.value, emulated.headers) == (
        record.topic,
        record.key,
        record.value,
        record.headers,
    )


@pytest.mark.cluster
def test_a_signup_reaches_user_events_in_its_trace(
    harness: Harness, user_events: TopicReader
) -> None:
    """Needs no database, so it also runs in cluster mode, against gluon-local's real topic:
    key the userId; the envelope with UserRegistered; a sampled traceparent in the signup
    request's trace; correlation_id; the router's id.

    Source: debezium-connectors-register.yaml (user-outbox-connector); ADR 0008 and its
    2026-11-05 amendment; docs/system-design.md "Envelope" (Kafka headers).
    """
    inbound = new_traceparent()
    trace = parse_traceparent(inbound)
    assert trace is not None
    user_id = signed_up(harness, new_email(), traceparent=inbound)["userId"]
    record = user_events.record("user-events", lambda r: r.key == user_id, timeout_s=90)
    envelope = json.loads(record.value or "")
    assert (envelope["eventType"], envelope["correlationId"]) == ("UserRegistered", user_id)
    assert envelope["payload"]["userId"] == user_id
    parent = parse_traceparent(record.headers.get("traceparent") or "")
    assert parent is not None, record.headers
    assert (parent.trace_id, parent.sampled) == (trace.trace_id, True)
    assert record.headers.get("correlation_id") == user_id
    assert is_uuid(record.headers.get("id") or ""), record.headers
