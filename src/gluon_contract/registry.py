# SPDX-License-Identifier: MIT

"""Kafka payload schemas from gluon's `registry/` (ADR 0003: git is the store).

`registry/<producer>/registry.json` lists every artifact with every version;
the last version is the current contract. Schemas are JSON Schema draft-07.
"""

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator

REGISTRY = Path(__file__).resolve().parents[4] / "registry"
"""gluon's registry/ (this repo lives at gluon/tests/contract)."""


def latest_schema(producer: str, artifact_id: str, *, root: Path = REGISTRY) -> dict[str, Any]:
    """The current schema of `artifact_id`, e.g. `user-events-UserRegistered`.

    Raises:
        KeyError: when the producer's registry has no such artifact.
    """
    document = json.loads((root / producer / "registry.json").read_text(encoding="utf-8"))
    for artifact in document["artifacts"]:
        if artifact["artifactId"] == artifact_id:
            schema: dict[str, Any] = artifact["versions"][-1]["schema"]
            return schema
    raise KeyError(f"{producer} has no artifact {artifact_id}")


def validation_errors(instance: Any, schema: dict[str, Any]) -> list[str]:
    """Every way `instance` breaks `schema` (draft-07); empty when it is valid."""
    return [error.message for error in Draft7Validator(schema).iter_errors(instance)]
