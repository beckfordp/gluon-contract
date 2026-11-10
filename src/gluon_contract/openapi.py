# SPDX-License-Identifier: MIT

"""The served OpenAPI spec as a yardstick for responses (RUST-1.4).

A response conforms when its operation documents its status, and either
documents no content and the body is empty, or documents the response's
media type and the body is valid against that schema (OpenAPI 3.1, so JSON
Schema 2020-12, `$ref`s resolved against the whole document).
"""

import json
import re
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry
from referencing.jsonschema import DRAFT202012

from gluon_contract.http import HttpResponse

SPEC_URI = "urn:gluon-contract:openapi"


def load_spec(text: str) -> dict[str, Any]:
    """An OpenAPI document from its YAML (or JSON) text."""
    spec: dict[str, Any] = yaml.safe_load(text)
    return spec


def _template_pattern(template: str) -> re.Pattern[str]:
    """`/users/{id}` as a pattern matching one segment per parameter."""
    parts = re.split(r"(\{[^}/]+\})", template)
    body = "".join("[^/]+" if part.startswith("{") else re.escape(part) for part in parts)
    return re.compile(f"^{body}$")


def operation_for(
    spec: dict[str, Any], method: str, path: str
) -> tuple[str, dict[str, Any]] | None:
    """The (path template, operation) a request would hit, or None."""
    for template, item in spec.get("paths", {}).items():
        operation = item.get(method.lower())
        if operation is not None and _template_pattern(template).match(path):
            return template, operation
    return None


def _absolute_refs(node: Any) -> Any:
    """A copy of `node` whose local `$ref`s point into the registered spec."""
    if isinstance(node, dict):
        return {
            key: (
                SPEC_URI + value
                if key == "$ref" and isinstance(value, str) and value.startswith("#")
                else _absolute_refs(value)
            )
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [_absolute_refs(item) for item in node]
    return node


def conformance(spec: dict[str, Any], method: str, path: str, response: HttpResponse) -> str | None:
    """None when `response` conforms to the spec, else why it doesn't."""
    found = operation_for(spec, method, path)
    if found is None:
        return f"no operation for {method} {path}"
    template, operation = found
    documented = operation.get("responses", {}).get(str(response.status))
    if documented is None:
        return f"status {response.status} is not documented for {method} {template}"
    content = documented.get("content")
    if not content:
        return (
            None
            if response.body == b""
            else f"a body where none is documented: {response.text[:80]!r}"
        )
    media_type = (response.header("Content-Type") or "").split(";")[0].strip()
    if media_type not in content:
        return f"{media_type or 'no Content-Type'} is not documented (only {', '.join(content)})"
    schema = content[media_type].get("schema")
    if schema is None:
        return None
    try:
        instance = json.loads(response.body)
    except ValueError:
        return f"body is not JSON: {response.text[:80]!r}"
    registry: Registry[Any] = Registry().with_resource(SPEC_URI, DRAFT202012.create_resource(spec))
    validator = Draft202012Validator(_absolute_refs(schema), registry=registry)
    errors = sorted(error.message for error in validator.iter_errors(instance))
    return "; ".join(errors) if errors else None
