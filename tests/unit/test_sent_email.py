# SPDX-License-Identifier: MIT

"""notification-service's captured `sent_email` rows, as seed data (gluon RPN-4)."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from gluon_contract.capture import load_exchange
from gluon_contract.formats import java_instant
from gluon_contract.notification_scenarios import O_CUST, O_GUEST, U_FLAKY, U_OK
from gluon_contract.sent_email import SentEmailRow, captured_rows, existing_at, parse_rows

SERVICE = "notification-service"
FLAKY_EVENT = "e0000000-0000-4000-8000-000000000050"
"""CAPTURE.sh step 6: the always-failing lookup, sent after the REST surface was recorded."""

ROW = (
    '{"id":"9f443147-73e5-488b-9c1d-553acbda1ef2",'
    '"source_event_id":"e0000000-0000-4000-8000-000000000001","event_type":"UserRegistered",'
    '"reason":null,"recipient_type":"email","recipient_key":"ada@example.com",'
    '"customer_id":"11111111-1111-4111-8111-111111111111","order_id":null,'
    '"subject":"Welcome to gshop","body":"Welcome.","status":"sent",'
    '"created_at":"2026-11-11T11:20:43.575212+00:00",'
    '"sent_at":"2026-11-11T11:20:43.641993+00:00","failed_at":null,"error":null,'
    '"recipient_email":"ada@example.com"}'
)


def row_at(created_at: datetime, event: str = "e1") -> SentEmailRow:
    """`ROW`, for another event, created at `created_at`."""
    return replace(parse_rows(ROW)[0], source_event_id=event, created_at=created_at)


# --- Parsing ---------------------------------------------------------------------------------


def test_a_row_parses_into_typed_columns() -> None:
    """Text as text, SQL null as None, timestamps as aware datetimes with their microseconds."""
    row = parse_rows(ROW + "\n")[0]
    assert row.id == "9f443147-73e5-488b-9c1d-553acbda1ef2"
    assert row.reason is None
    assert row.order_id is None
    assert row.created_at == datetime(2026, 11, 11, 11, 20, 43, 575212, tzinfo=UTC)
    assert row.sent_at == datetime(2026, 11, 11, 11, 20, 43, 641993, tzinfo=UTC)
    assert row.failed_at is None
    assert row.recipient_email == "ada@example.com"


def test_a_row_missing_a_column_is_refused_by_name() -> None:
    """The dump is the seed: a row without every column can't be inserted as captured."""
    with pytest.raises(ValueError, match="line 1: missing column recipient_email"):
        parse_rows(ROW.replace(',"recipient_email":"ada@example.com"', ""))


def test_a_line_that_is_not_json_is_refused_by_number() -> None:
    """Says which line."""
    with pytest.raises(ValueError, match="line 2 is not JSON"):
        parse_rows(ROW + "\n{oops\n")


def test_the_captured_rows_all_parse() -> None:
    """The capture's 20 rows, one per source event, each with an aware created_at.

    Source: capture db/sent-email.jsonl (checked against the scenario table by
    notification_capture).
    """
    rows = captured_rows()
    assert len(rows) == 20
    assert len({row.source_event_id for row in rows}) == 20
    assert all(row.created_at.tzinfo is not None for row in rows)


# --- Which rows existed when an exchange was captured ---------------------------------------


def test_existing_at_keeps_the_rows_created_before_the_dates_second_ends() -> None:
    """`Date` has whole seconds: a row from within that second existed; one after it didn't."""
    within = row_at(datetime(2026, 11, 11, 11, 21, 32, 999999, tzinfo=UTC), "within")
    after = row_at(datetime(2026, 11, 11, 11, 21, 33, tzinfo=UTC), "after")
    assert existing_at([within, after], "Wed, 11 Nov 2026 11:21:32 GMT") == [within]


def test_emails_all_was_captured_before_the_failed_send() -> None:
    """19 rows existed when `emails-all` was recorded: all but the flaky lookup's.

    Source: capture http/emails-all.txt (Date) and db/sent-email.jsonl.
    """
    date = load_exchange("emails-all", service=SERVICE).header("Date")
    assert date is not None
    rows = existing_at(captured_rows(), date)
    assert len(rows) == 19
    assert FLAKY_EVENT not in {row.source_event_id for row in rows}


# --- The seed reproduces the capture's answers -----------------------------------------------


def as_response(row: SentEmailRow) -> dict[str, Any]:
    """A row as the Scala service's `GET /emails` renders it (capture http/emails-*.txt).

    Here, not in `src/`, on purpose: a check compares with the captured body, never
    with an answer built from the rows.
    """

    def instant(value: datetime | None) -> str | None:
        return None if value is None else java_instant(value)

    return {
        "id": row.id,
        "sourceEventId": row.source_event_id,
        "eventType": row.event_type,
        "reason": row.reason,
        "recipientType": row.recipient_type,
        "recipientKey": row.recipient_key,
        "recipientEmail": row.recipient_email,
        "customerId": row.customer_id,
        "orderId": row.order_id,
        "subject": row.subject,
        "body": row.body,
        "status": row.status,
        "createdAt": instant(row.created_at),
        "sentAt": instant(row.sent_at),
        "failedAt": instant(row.failed_at),
        "error": row.error,
    }


# Each captured /emails answer and its filters (customerId, orderId), from CAPTURE.sh's
# `cap` lines; None is a parameter not sent.
CAPTURED_ANSWERS = {
    "emails-all": (None, None),
    "emails-customer": (U_OK, None),
    "emails-order": (None, O_CUST),
    "emails-both": (U_OK, O_CUST),
    "emails-guest-order": (None, O_GUEST),
    "emails-none": ("00000000-0000-0000-0000-000000000000", None),
    "emails-empty-param": ("", None),
    "emails-not-uuid": ("not-a-uuid", None),
    "emails-unknown-param": (None, None),
    "emails-trailing-slash": (None, None),
    "emails-traceparent": (None, O_CUST),
    "cors-simple": (None, None),
    "emails-after-flaky": (U_FLAKY, None),
}


@pytest.mark.parametrize("captured", CAPTURED_ANSWERS)
def test_the_seed_reproduces_every_captured_emails_answer(captured: str) -> None:
    """The rows that existed when an answer was recorded, filtered as its query says and
    newest first, are exactly its body: seeding them lets a check expect the capture.

    Source: capture http/<captured>.txt, db/sent-email.jsonl; openapi.yaml ("newest
    first", filters "combined with AND").
    """
    exchange = load_exchange(captured, service=SERVICE)
    date = exchange.header("Date")
    assert date is not None
    customer, order = CAPTURED_ANSWERS[captured]
    rows = [
        row
        for row in existing_at(captured_rows(), date)
        if (customer is None or row.customer_id == customer)
        and (order is None or row.order_id == order)
    ]
    rows.sort(key=lambda row: row.created_at, reverse=True)
    assert [as_response(row) for row in rows] == exchange.json()
