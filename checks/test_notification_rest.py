# SPDX-License-Identifier: MIT

"""REST contract of notification-service (gluon RPN-4; ADR 0029).

Expectations come from the reference: the capture
`contracts/notification-service/20261111` (`http/*.txt`, `openapi.yaml`) and the
Scala service's `EmailRoutesSuite`. Never from the implementation under test.
Nothing creates `sent_email` rows through the API until the consumers exist
(RPN-10 on), so `/emails` checks seed the table with the capture's own rows
(`gluon_contract.sent_email`): those that existed when `emails-all` was recorded.
JSON bodies compare exactly as parsed JSON; framework text errors on status,
Content-Type and text (as user-service's REST group, RUST-1.3).
"""

from typing import Any

import psycopg
import pytest

from gluon_contract.capture import load_exchange
from gluon_contract.expect import assert_same, assert_same_cors, assert_text_error
from gluon_contract.harness import Harness
from gluon_contract.http import HttpResponse, request
from gluon_contract.ns_scenarios import O_CUST, O_GUEST, U_FLAKY, U_GONE, U_OK
from gluon_contract.sent_email import SentEmailRow, captured_rows, existing_at, insert

pytestmark = pytest.mark.service("notification-service")
"""notification-service's contract: deselected in a run for another service (RPN-3)."""

SERVICE = "notification-service"
FLAKY_EVENT = "e0000000-0000-4000-8000-000000000050"
"""CAPTURE.sh step 6: the always-failing lookup, sent after the REST surface was recorded."""

type Db = psycopg.Connection[tuple[Any, ...]]


def call(harness: Harness, method: str, path: str, **kwargs: Any) -> HttpResponse:
    """One request to the service under test."""
    return request(harness.base_url, method, path, **kwargs)


def same(response: HttpResponse, captured: str) -> None:
    """Status, Content-Type and JSON body as notification-service's capture `captured`."""
    assert_same(response, captured, service=SERVICE)


def captured_text(captured: str) -> str:
    """The body of notification-service's captured exchange, as text."""
    return load_exchange(captured, service=SERVICE).text


@pytest.fixture
def seeded(db: Db) -> list[SentEmailRow]:
    """`sent_email` holds exactly the rows that existed when `emails-all` was recorded."""
    date = load_exchange("emails-all", service=SERVICE).header("Date")
    assert date is not None
    rows = existing_at(captured_rows(), date)
    db.execute("delete from sent_email")
    insert(db, rows)
    return rows


# --- GET /emails -------------------------------------------------------------------------------


def test_emails_lists_every_email_newest_first(harness: Harness, seeded: object) -> None:
    """200, every row, newest first, each with all 16 fields (absent values as null).

    Source: capture http/emails-all.txt; openapi.yaml ("newest first"); EmailRoutesSuite.
    """
    same(call(harness, "GET", "/emails"), "emails-all")


@pytest.mark.parametrize(
    ("query", "captured"),
    [
        (f"customerId={U_OK}", "emails-customer"),
        (f"orderId={O_CUST}", "emails-order"),
        (f"customerId={U_OK}&orderId={O_CUST}", "emails-both"),
        (f"orderId={O_GUEST}", "emails-guest-order"),
        ("customerId=00000000-0000-0000-0000-000000000000", "emails-none"),
    ],
    ids=["customer", "order", "both", "guest-order", "no-match"],
)
def test_emails_filters_as_captured(
    harness: Harness, seeded: object, query: str, captured: str
) -> None:
    """customerId and orderId each filter, combined with AND; no match is 200 [].

    Source: capture http/<captured>.txt; openapi.yaml ("combined with AND"); EmailRoutesSuite.
    """
    same(call(harness, "GET", f"/emails?{query}"), captured)


def test_an_empty_filter_matches_nothing(harness: Harness, seeded: object) -> None:
    """`customerId=` filters on the empty string: 200 [], not every email.

    Source: capture http/emails-empty-param.txt. Implicit behaviour N3.
    """
    same(call(harness, "GET", "/emails?customerId="), "emails-empty-param")


def test_filters_compare_text_not_uuids(harness: Harness, seeded: object) -> None:
    """A filter is any text, matched exactly: `not-a-uuid` is no 400, it finds its row.

    Source: capture http/emails-not-uuid.txt; openapi.yaml (parameters are strings).
    Implicit behaviour N4.
    """
    same(call(harness, "GET", "/emails?customerId=not-a-uuid"), "emails-not-uuid")


def test_a_repeated_filter_is_a_plain_text_400(harness: Harness, seeded: object) -> None:
    """400 text/plain "Invalid value for: query parameter customerId (multiple values)",
    which the OpenAPI spec doesn't list.

    Source: capture http/emails-repeated-param.txt. Implicit behaviour N5.
    """
    response = call(harness, "GET", f"/emails?customerId={U_OK}&customerId={U_GONE}")
    assert_text_error(response, 400, captured_text("emails-repeated-param"))


def test_a_trailing_slash_is_the_same_resource(harness: Harness, seeded: object) -> None:
    """`/emails/` answers as `/emails`.

    Source: capture http/emails-trailing-slash.txt. Implicit behaviour N6.
    """
    same(call(harness, "GET", "/emails/"), "emails-trailing-slash")


def test_unknown_query_parameters_are_ignored(harness: Harness, seeded: object) -> None:
    """`?foo=bar` answers as no parameters at all.

    Source: capture http/emails-unknown-param.txt. Implicit behaviour N7.
    """
    same(call(harness, "GET", "/emails?foo=bar"), "emails-unknown-param")


def test_a_traceparent_does_not_change_the_answer(harness: Harness, seeded: object) -> None:
    """An inbound W3C traceparent is accepted; the answer is the untraced one.

    Source: capture http/emails-traceparent.txt (the capture's traceparent).
    """
    response = call(
        harness,
        "GET",
        f"/emails?orderId={O_CUST}",
        headers={"traceparent": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"},
    )
    same(response, "emails-traceparent")


def test_a_failed_send_shows_when_and_why(harness: Harness, seeded: object, db: Db) -> None:
    """A failed row: status "failed", failedAt set, sentAt null, the error text.

    Source: capture http/emails-after-flaky.txt (the row CAPTURE.sh step 6 made).
    """
    insert(db, [row for row in captured_rows() if row.source_event_id == FLAKY_EVENT])
    try:
        same(call(harness, "GET", f"/emails?customerId={U_FLAKY}"), "emails-after-flaky")
    finally:
        db.execute("delete from sent_email where source_event_id = %s", (FLAKY_EVENT,))


@pytest.mark.parametrize(
    ("method", "captured"),
    [("POST", "emails-post"), ("DELETE", "emails-delete"), ("HEAD", "emails-head")],
)
def test_emails_with_another_method_is_405(harness: Harness, method: str, captured: str) -> None:
    """405 text/plain "Method Not Allowed" (HEAD: no body); there is no write API.

    Source: capture http/emails-post.txt, emails-delete.txt, emails-head.txt.
    """
    kwargs: dict[str, Any] = (
        {"body": b"{}", "headers": {"Content-Type": "application/json"}} if method == "POST" else {}
    )
    response = call(harness, method, "/emails", **kwargs)
    assert_text_error(response, 405, captured_text(captured))


# --- CORS --------------------------------------------------------------------------------------

ORIGIN = {"Origin": "http://localhost:5173"}
"""gshop's dev origin, as CAPTURE.sh sends it."""


def preflight(harness: Harness, request_headers: str) -> HttpResponse:
    """OPTIONS /emails asking for GET with `request_headers`, as CAPTURE.sh asks."""
    return call(
        harness,
        "OPTIONS",
        "/emails",
        headers={
            **ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": request_headers,
        },
    )


def test_a_cors_preflight_is_answered_as_captured(harness: Harness) -> None:
    """200, empty; any origin, PATCH/PUT/GET/POST/DELETE, Content-Type; Vary; no credentials.

    Source: capture http/cors-preflight.txt (header lists compared as sets).
    """
    response = preflight(harness, "content-type")
    assert_same_cors(response, "cors-preflight", service=SERVICE)
    assert response.body == b"", response.text[:200]


def test_a_preflight_for_a_disallowed_header_gets_no_allow_headers(harness: Harness) -> None:
    """Asking for `Authorization`: still 200 and empty, with only `Vary`, no Allow-* at all,
    so the browser refuses the request.

    Source: capture http/cors-preflight-bad-header.txt. Implicit behaviour N8.
    """
    response = preflight(harness, "authorization")
    assert_same_cors(response, "cors-preflight-bad-header", service=SERVICE)
    assert response.body == b"", response.text[:200]


def test_a_cross_origin_request_gets_allow_origin(harness: Harness, seeded: object) -> None:
    """`Access-Control-Allow-Origin: *` and no other CORS header (nothing exposed); the
    answer itself unchanged.

    Source: capture http/cors-simple.txt.
    """
    response = call(harness, "GET", "/emails", headers=ORIGIN)
    assert_same_cors(response, "cors-simple", service=SERVICE)
    same(response, "cors-simple")
