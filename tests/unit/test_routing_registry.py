# SPDX-License-Identifier: MIT

"""Connector routing and registry schemas (RUST-1.6 helpers)."""

import pytest

from gluon_contract.registry import latest_schema, validation_errors
from gluon_contract.routing import load_connector, route

CONNECTOR = {
    "transforms.outbox.route.topic.replacement": "user-events",
    "transforms.outbox.table.field.event.key": "aggregate_id",
    "transforms.outbox.table.field.event.payload": "payload",
    "transforms.outbox.table.fields.additional.placement": (
        "trace_parent:header:traceparent,correlation_id:header"
    ),
}
ROW = {
    "aggregate_id": "691b03e8-f1d7-45d9-a561-5183ffae9d0b",
    "payload": '{"eventType": "UserRegistered"}',
    "trace_parent": "00-a431925467471e85affc7f942350d759-4fabf80327a661c4-03",
    "correlation_id": "691b03e8-f1d7-45d9-a561-5183ffae9d0b",
}


def test_a_row_routes_as_the_event_router_would() -> None:
    """Topic from the replacement, key and value from their fields, extra fields as headers."""
    record = route(ROW, CONNECTOR)
    assert record.topic == "user-events"
    assert record.key == ROW["aggregate_id"]
    assert record.value == ROW["payload"]
    assert record.headers == {
        "traceparent": ROW["trace_parent"],
        "correlation_id": ROW["correlation_id"],
    }


def test_a_null_field_gives_a_header_with_no_value() -> None:
    """A row written outside a span has no trace_parent: the router still adds a
    traceparent header, with a null value (seen on the sandbox CDC stack; purekafka
    KafkaTracing.extractCarrier skips such headers: "Debezium writes a NULL outbox
    trace_parent that way")."""
    assert route({**ROW, "trace_parent": None}, CONNECTOR).headers["traceparent"] is None


def test_the_registered_user_connector_is_read_from_gluon() -> None:
    """The config Debezium actually runs with (infra/k8s/local-infra)."""
    connector = load_connector("user-outbox-connector.json")
    assert connector["transforms.outbox.route.topic.replacement"] == "user-events"
    assert connector["table.include.list"] == "public.outbox_events"
    with pytest.raises(KeyError, match="no-such-connector"):
        load_connector("no-such-connector.json")


def test_the_latest_user_registered_schema_validates_payloads() -> None:
    """registry/user-service/registry.json, last version: closed, both fields strings."""
    schema = latest_schema("user-service", "user-events-UserRegistered")
    assert validation_errors({"userId": "u", "email": "e"}, schema) == []
    assert validation_errors({"userId": "u"}, schema)
    assert validation_errors({"userId": "u", "email": "e", "extra": 1}, schema)
    with pytest.raises(KeyError, match="nope"):
        latest_schema("user-service", "nope")


def test_the_router_adds_the_row_id_as_the_id_header() -> None:
    """EventRouter's default `table.field.event.id` (id) becomes an `id` header, as the real
    connector's records carry (RUST-1.8: seen on the sandbox CDC stack)."""
    record = route({**ROW, "id": "7921e9e4-d301-4976-a461-cdcdc183258d"}, CONNECTOR)
    assert record.headers["id"] == "7921e9e4-d301-4976-a461-cdcdc183258d"
    assert list(record.headers) == ["id", "traceparent", "correlation_id"]
