# SPDX-License-Identifier: MIT

"""Comparing a response with a captured one, for any service's checks (gluon RPN-4)."""

import pytest

from gluon_contract.capture import load_exchange
from gluon_contract.expect import TEXT_PLAIN, assert_same, assert_same_cors, assert_text_error
from gluon_contract.http import HttpResponse

NOTIFICATION = "notification-service"
NOT_FOUND = HttpResponse(404, (("Content-Type", TEXT_PLAIN),), b"Not found")
"""What a build without the route answers."""


def json_response(status: int, body: bytes) -> HttpResponse:
    """A JSON response as the Scala services send it."""
    return HttpResponse(status, (("Content-Type", "application/json"),), body)


# --- assert_same -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("service", "captured"),
    [(NOTIFICATION, "emails-all"), (NOTIFICATION, "emails-none"), ("user-service", "users-404")],
)
def test_the_captured_answer_itself_is_the_same(service: str, captured: str) -> None:
    """Either service's capture, read through its `service`."""
    assert_same(load_exchange(captured, service=service), captured, service=service)


def test_another_status_fails_naming_the_capture_and_both_statuses() -> None:
    """The status is compared first, so a missing route reads as the 404 it is."""
    with pytest.raises(AssertionError) as failure:
        assert_same(NOT_FOUND, "emails-all", service=NOTIFICATION)
    message = str(failure.value)
    assert "emails-all" in message
    assert "expected 200 application/json" in message
    assert f"got 404 {TEXT_PLAIN}" in message
    assert "'Not found'" in message


def test_a_different_json_body_fails_showing_both() -> None:
    """Same status and Content-Type, another body: both bodies in the message."""
    with pytest.raises(AssertionError, match=r"emails-none: body expected \[\], got \[1\]"):
        assert_same(json_response(200, b"[1]"), "emails-none", service=NOTIFICATION)


def test_a_body_that_is_not_json_fails_quoting_it() -> None:
    """A JSON answer was captured; text instead says so."""
    with pytest.raises(AssertionError, match="emails-none: body is not JSON: 'oops'"):
        assert_same(json_response(200, b"oops"), "emails-none", service=NOTIFICATION)


# --- assert_text_error -----------------------------------------------------------------------


def test_a_text_error_matches_exactly_or_by_prefix() -> None:
    """Exact text, or (for decode failures) the text's start."""
    assert_text_error(NOT_FOUND, 404, "Not found")
    assert_text_error(NOT_FOUND, 404, "Not", prefix=True)


def test_a_text_error_with_another_status_fails_naming_both() -> None:
    """Status and Content-Type first, as for assert_same."""
    with pytest.raises(AssertionError, match=f"expected 405 {TEXT_PLAIN}, got 404 {TEXT_PLAIN}"):
        assert_text_error(NOT_FOUND, 405, "Method Not Allowed")


def test_a_text_error_with_other_text_fails_showing_both() -> None:
    """Exact and prefix comparisons each say which they were."""
    with pytest.raises(AssertionError, match="text expected 'Nope', got 'Not found'"):
        assert_text_error(NOT_FOUND, 404, "Nope")
    with pytest.raises(AssertionError, match="text expected to start 'Nope', got 'Not found'"):
        assert_text_error(NOT_FOUND, 404, "Nope", prefix=True)


# --- assert_same_cors ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("service", "captured"),
    [
        (NOTIFICATION, "cors-preflight"),
        (NOTIFICATION, "cors-preflight-bad-header"),
        (NOTIFICATION, "cors-simple"),
        ("user-service", "cors-preflight"),
    ],
)
def test_a_captured_cors_answer_itself_is_the_same(service: str, captured: str) -> None:
    """Either service's capture, read through its `service`."""
    assert_same_cors(load_exchange(captured, service=service), captured, service=service)


def test_cors_header_lists_compare_as_sets() -> None:
    """The methods in another order, header names in another case: the same answer."""
    response = HttpResponse(
        200,
        (
            ("access-control-allow-origin", "*"),
            ("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE"),
            ("Access-Control-Allow-Headers", "Content-Type"),
            ("Vary", "Access-Control-Request-Headers, Access-Control-Request-Method"),
        ),
        b"",
    )
    assert_same_cors(response, "cors-preflight", service=NOTIFICATION)


def test_a_missing_cors_header_fails_naming_it() -> None:
    """A preflight answered without the allow headers: each named, expected and got."""
    refused = load_exchange("cors-preflight-bad-header", service=NOTIFICATION)
    with pytest.raises(AssertionError) as failure:
        assert_same_cors(refused, "cors-preflight", service=NOTIFICATION)
    message = str(failure.value)
    assert message.startswith("cors-preflight: ")
    assert "Access-Control-Allow-Origin: expected ['*'], got []" in message
    assert "Access-Control-Allow-Headers: expected ['Content-Type'], got []" in message


def test_an_extra_cors_header_fails_naming_it() -> None:
    """Credentials allowed where the capture has none."""
    captured = load_exchange("cors-simple", service=NOTIFICATION)
    response = HttpResponse(
        200, (*captured.headers, ("Access-Control-Allow-Credentials", "true")), captured.body
    )
    with pytest.raises(
        AssertionError, match=r"Access-Control-Allow-Credentials: expected \[\], got \['true'\]"
    ):
        assert_same_cors(response, "cors-simple", service=NOTIFICATION)


def test_a_cors_answer_with_another_status_fails_naming_both() -> None:
    """Status first: a missing route reads as its 404."""
    with pytest.raises(
        AssertionError, match="cors-preflight: expected 200, got 404; body 'Not found'"
    ):
        assert_same_cors(NOT_FOUND, "cors-preflight", service=NOTIFICATION)


def test_vary_is_compared_too() -> None:
    """A preflight answer without `Vary` (caches would mix answers for different requests)."""
    without_vary = HttpResponse(200, (), b"")
    with pytest.raises(
        AssertionError,
        match=r"Vary: expected \['Access-Control-Request-Headers', 'Access-Control-Request-Meth",
    ):
        assert_same_cors(without_vary, "cors-preflight-bad-header", service=NOTIFICATION)
