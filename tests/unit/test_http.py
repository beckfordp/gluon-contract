# SPDX-License-Identifier: MIT

"""The raw HTTP response type (RUST-1.3 helpers)."""

import pytest

from gluon_contract.http import HttpResponse, json_body


def response(*headers: tuple[str, str], body: bytes = b"") -> HttpResponse:
    """A response with the given headers."""
    return HttpResponse(status=200, headers=headers, body=body)


def test_headers_are_case_insensitive_and_lists_are_sets() -> None:
    """Repeated headers and comma lists both count; order within a list doesn't."""
    r = response(
        ("Access-Control-Allow-Methods", "PATCH, PUT"),
        ("access-control-allow-methods", "GET,POST, DELETE"),
        ("Content-Type", "application/json"),
    )
    assert r.header("CONTENT-TYPE") == "application/json"
    assert r.header_set("Access-Control-Allow-Methods") == {"PATCH", "PUT", "GET", "POST", "DELETE"}
    assert r.header("Allow") is None
    assert r.header_set("Allow") == set()


def test_text_and_json_bodies() -> None:
    """Bodies decode as UTF-8 text or JSON; a non-JSON body says what it was."""
    assert response(body=b'{"a":1}').json() == {"a": 1}
    assert response(body=b"Not found").text == "Not found"
    with pytest.raises(ValueError, match="Not found"):
        response(body=b"Not found").json()


def test_json_body_is_compact_utf8() -> None:
    """Request bodies go out as compact UTF-8 JSON, non-ASCII unescaped."""
    assert json_body({"email": "äda@example.com"}) == '{"email":"äda@example.com"}'.encode()
