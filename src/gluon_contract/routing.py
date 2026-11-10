# SPDX-License-Identifier: MIT

"""What Debezium's Outbox Event Router makes of an outbox row (ADR 0008).

The harness doesn't run Debezium in isolated mode; it applies the connector's
registered routing to the row instead. The config is the one gluon-local
registers: `infra/k8s/local-infra/debezium-connectors-register.yaml`.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

CONNECTORS_FILE = (
    Path(__file__).resolve().parents[4] / "infra/k8s/local-infra/debezium-connectors-register.yaml"
)
PREFIX = "transforms.outbox."


@dataclass(frozen=True, slots=True)
class RoutedRecord:
    """The Kafka record the router would produce."""

    topic: str
    key: str
    value: str
    headers: dict[str, str | None]
    """A null field's header has no value (None), as Debezium writes it."""


def load_connector(name: str, *, path: Path = CONNECTORS_FILE) -> dict[str, str]:
    """The connector config registered under `name` (a ConfigMap data key).

    Raises:
        KeyError: when no document in the file holds `name`.
    """
    for document in yaml.safe_load_all(path.read_text(encoding="utf-8")):
        data = (document or {}).get("data") or {}
        if name in data:
            config: dict[str, str] = json.loads(data[name])
            return config
    raise KeyError(f"{path} registers no {name}")


def route(row: Mapping[str, Any], connector: Mapping[str, str]) -> RoutedRecord:
    """Applies the router's topic, key, value and header placement to `row`.

    `row[payload field]` must be the column's text as Postgres renders it (the
    router passes it through unchanged: `expand.json.payload=false`). The row's
    id (`table.field.event.id`, default `id`) comes first as an `id` header, as
    the real router adds it (seen on the sandbox CDC stack, RUST-1.8).
    """
    headers: dict[str, str | None] = {}
    id_field = connector.get(PREFIX + "table.field.event.id", "id")
    if row.get(id_field) is not None:
        headers["id"] = str(row[id_field])
    for placement in connector[PREFIX + "table.fields.additional.placement"].split(","):
        field, _, rest = placement.strip().partition(":")
        where, _, alias = rest.partition(":")
        if where == "header":
            value = row.get(field)
            headers[alias or field] = None if value is None else str(value)
    return RoutedRecord(
        topic=connector[PREFIX + "route.topic.replacement"],
        key=str(row[connector[PREFIX + "table.field.event.key"]]),
        value=str(row[connector[PREFIX + "table.field.event.payload"]]),
        headers=headers,
    )
