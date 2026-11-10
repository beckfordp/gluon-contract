# SPDX-License-Identifier: MIT

"""Parsing captured `curl -si` exchanges (RUST-1.3 helpers)."""

import pytest

from gluon_contract.capture import CaptureError, load_exchange, parse_exchange

RAW = (
    b"HTTP/1.1 409 Conflict\r\n"
    b"Date: Mon, 09 Nov 2026 18:43:19 GMT\r\n"
    b"Content-Type: application/json\r\n"
    b"Vary: Access-Control-Request-Method, Access-Control-Request-Headers\r\n"
    b"Content-Length: 53\r\n"
    b"\r\n"
    b'{"error":"An account with this email already exists"}'
)


def test_a_capture_parses_into_status_headers_and_body() -> None:
    """Status line, headers (case-insensitive), and the body bytes as sent."""
    exchange = parse_exchange(RAW)
    assert exchange.status == 409
    assert exchange.header("content-type") == "application/json"
    assert exchange.header_set("VARY") == {
        "Access-Control-Request-Method",
        "Access-Control-Request-Headers",
    }
    assert exchange.json() == {"error": "An account with this email already exists"}
    assert exchange.header("X-Missing") is None


def test_an_empty_body_and_lf_only_line_endings_are_fine() -> None:
    """curl on some platforms writes bare LFs; a 200 may have no body."""
    exchange = parse_exchange(b"HTTP/1.1 200 OK\nContent-Length: 0\n\n")
    assert (exchange.status, exchange.body) == (200, b"")


def test_garbage_is_a_capture_error() -> None:
    """A file that isn't an HTTP response says so."""
    with pytest.raises(CaptureError, match="not an HTTP response"):
        parse_exchange(b"hello")


def test_the_committed_capture_loads() -> None:
    """The committed capture's 409 is the one the checks will compare with."""
    exchange = load_exchange("signup-409")
    assert exchange.status == 409
    assert exchange.json() == {"error": "An account with this email already exists"}
