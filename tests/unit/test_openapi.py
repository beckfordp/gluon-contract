# SPDX-License-Identifier: MIT

"""OpenAPI lookup and conformance (RUST-1.4 helper), against the captured spec."""

import json

import pytest

from gluon_contract.capture import capture_file
from gluon_contract.http import HttpResponse
from gluon_contract.openapi import conformance, load_spec, operation_for

SPEC = load_spec(capture_file("openapi.yaml").read_text())
JSON_TYPE = {"Content-Type": "application/json"}


def response(
    status: int, body: object = None, content_type: str | None = "application/json"
) -> HttpResponse:
    """A response with a JSON body (or raw bytes, or nothing)."""
    raw = body if isinstance(body, bytes) else b"" if body is None else json.dumps(body).encode()
    headers = () if content_type is None else (("Content-Type", content_type),)
    return HttpResponse(status=status, headers=headers, body=raw)


def test_a_concrete_path_finds_its_templated_operation() -> None:
    """/users/<id> matches /users/{id}; method matters; unknown paths find nothing."""
    found = operation_for(SPEC, "GET", "/users/691b03e8-f1d7-45d9-a561-5183ffae9d0b")
    assert found is not None
    assert (found[0], found[1]["operationId"]) == ("/users/{id}", "getUsersId")
    assert operation_for(SPEC, "POST", "/auth/signup") is not None
    assert operation_for(SPEC, "GET", "/auth/signup") is None
    assert operation_for(SPEC, "GET", "/no-such-path") is None
    assert operation_for(SPEC, "GET", "/users/a/b") is None


def test_a_documented_json_response_conforms() -> None:
    """201 {userId, token}: conforms."""
    body = {"userId": "5b6c7d8e-9f0a-4b1c-8d2e-3f4a5b6c7d8e", "token": "t"}
    assert conformance(SPEC, "POST", "/auth/signup", response(201, body)) is None


def test_a_body_missing_a_required_field_does_not() -> None:
    """The schema's required fields are enforced, through the $ref."""
    reason = conformance(SPEC, "POST", "/auth/signup", response(201, {"userId": "x"}))
    assert reason is not None
    assert "token" in reason


def test_an_anyof_error_body_conforms() -> None:
    """400's schema is anyOf two ErrorResponse refs."""
    assert conformance(SPEC, "POST", "/auth/signup", response(400, {"error": "x"})) is None


def test_a_plain_text_body_where_json_is_documented_does_not() -> None:
    """A decode failure's text/plain 400 isn't the documented application/json."""
    reason = conformance(
        SPEC, "POST", "/auth/signup", response(400, b"Invalid value", "text/plain; charset=UTF-8")
    )
    assert reason is not None
    assert "text/plain" in reason


def test_an_undocumented_status_does_not() -> None:
    """GET /users/{id} documents 200 and 404, not 400."""
    reason = conformance(SPEC, "GET", "/users/x", response(400, b"x", "text/plain"))
    assert reason == "status 400 is not documented for GET /users/{id}"


def test_no_operation_does_not() -> None:
    """An unknown path or method has no operation to conform to."""
    assert (
        conformance(SPEC, "GET", "/nope", response(404, b"", None)) == "no operation for GET /nope"
    )


@pytest.mark.parametrize(("body", "conforms"), [(None, True), (b"surprise", False)])
def test_a_response_documented_without_content_must_be_empty(
    body: bytes | None, conforms: bool
) -> None:
    """/health's 200 has no content: an empty body conforms, anything else doesn't."""
    reason = conformance(SPEC, "GET", "/health", response(200, body, None))
    assert (reason is None) == conforms, reason
