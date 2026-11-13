# SPDX-License-Identifier: MIT

"""Comparing a response with the reference, for any service's checks (gluon RPN-4).

The same comparisons as user-service's REST checks (`checks/test_rest.py`, RUST-1.3:
JSON bodies exactly as parsed JSON, framework text errors on status, Content-Type
and the exact text or its prefix), for a service named by the caller. pytest doesn't
rewrite asserts outside test modules, so each failure spells out the capture,
expected and actual itself, status first: a missing route reads as its 404.
"""

from gluon_contract.capture import load_exchange
from gluon_contract.http import HttpResponse

TEXT_PLAIN = "text/plain; charset=UTF-8"
"""The Content-Type of tapir's text errors."""


def _head(response: HttpResponse) -> str:
    """Status and Content-Type, as a failure shows them."""
    return f"{response.status} {response.header('Content-Type')}"


def assert_same(actual: HttpResponse, captured: str, *, service: str) -> None:
    """Status, Content-Type and JSON body exactly as in the service's capture `http/<captured>.txt`.

    Raises:
        AssertionError: naming the capture, with what was expected and what came.
    """
    expected = load_exchange(captured, service=service)
    if (actual.status, actual.header("Content-Type")) != (
        expected.status,
        expected.header("Content-Type"),
    ):
        raise AssertionError(
            f"{captured}: expected {_head(expected)}, got {_head(actual)}; "
            f"body {actual.text[:200]!r}"
        )
    try:
        body = actual.json()
    except ValueError as error:
        raise AssertionError(f"{captured}: {error}") from error
    if body != expected.json():
        raise AssertionError(
            f"{captured}: body expected {expected.text[:500]}, got {actual.text[:500]}"
        )


def assert_text_error(
    actual: HttpResponse, status: int, text: str, *, prefix: bool = False
) -> None:
    """A framework error: plain text, exact or (for decode failures) exact up to the detail.

    Raises:
        AssertionError: with what was expected and what came.
    """
    if (actual.status, actual.header("Content-Type")) != (status, TEXT_PLAIN):
        raise AssertionError(
            f"expected {status} {TEXT_PLAIN}, got {_head(actual)}; body {actual.text[:200]!r}"
        )
    if prefix and not actual.text.startswith(text):
        raise AssertionError(f"text expected to start {text!r}, got {actual.text[:200]!r}")
    if not prefix and actual.text != text:
        raise AssertionError(f"text expected {text!r}, got {actual.text[:200]!r}")


CORS_HEADERS = (
    "Access-Control-Allow-Origin",
    "Access-Control-Allow-Methods",
    "Access-Control-Allow-Headers",
    "Access-Control-Expose-Headers",
    "Access-Control-Allow-Credentials",
    "Access-Control-Max-Age",
    "Vary",
)
"""Every header a CORS answer may carry (as user-service's REST group compares them)."""


def assert_same_cors(actual: HttpResponse, captured: str, *, service: str) -> None:
    """Status, and every CORS header as in the capture: lists compared as sets, a header
    the capture lacks must be absent.

    Raises:
        AssertionError: naming the capture and each header that differs.
    """
    expected = load_exchange(captured, service=service)
    if actual.status != expected.status:
        raise AssertionError(
            f"{captured}: expected {expected.status}, got {actual.status}; "
            f"body {actual.text[:200]!r}"
        )
    differences = [
        f"{name}: expected {sorted(expected.header_set(name))}, "
        f"got {sorted(actual.header_set(name))}"
        for name in CORS_HEADERS
        if actual.header_set(name) != expected.header_set(name)
    ]
    if differences:
        raise AssertionError(f"{captured}: " + "; ".join(differences))
