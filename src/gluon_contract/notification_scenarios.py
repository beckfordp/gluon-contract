# SPDX-License-Identifier: MIT

"""What notification-service's capture drove, and what it must have done (gluon PLAN.md RPN-1).

Written from the capture's `CAPTURE.sh` (`contracts/notification-service/20261111/`):
its stub fixtures (step 2), and every record it publishes (step 4, then step 6's
always-failing lookup), in order, each with the comment beside it. For each
record: the `sent_email` row it makes, if any, and whether it is dead-lettered.

What no comment states is taken from the capture and marked `(capture)`: the
subjects, the `error` texts, and `customer_id` staying empty when an order
lookup finds no recipient. The capture check (`notification_capture`) holds the capture
to this table; the consumer checks reuse it (RPN-10 on).
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass

# --- stub.py's fixtures (CAPTURE.sh step 2) ------------------------------------

U_OK = "11111111-1111-4111-8111-111111111111"
"""200, ada@example.com."""
U_GONE = "22222222-2222-4222-8222-222222222222"
"""404."""
U_FLAKY = "33333333-3333-4333-8333-333333333333"
"""500, always (transient)."""
O_CUST = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
"""Customer U_OK."""
O_GUEST = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
"""Customer U_GONE, guestEmail guest@example.com."""
O_NOGUEST = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
"""Customer U_GONE, no guestEmail."""
O_GONE = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
"""404."""
ADA = "ada@example.com"
GUEST = "guest@example.com"

TOPICS = ("user-events", "order-events", "payment-events", "fulfilment-events")
"""The input topics, as CAPTURE.sh creates them."""
DLQ_TOPICS = tuple(f"{topic}-dlq" for topic in TOPICS)
"""Their dead-letter topics, dumped to `kafka/<topic>-dlq.txt`."""

TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
"""The `traceparent` header on the first record of each topic (and on event 50)."""

TIMESTAMP = '"timestamp":"2026-11-10T12:00:00Z"'

# (capture): the subject of each event type's email.
SUBJECTS: Mapping[str, str] = {
    "UserRegistered": "Welcome to gshop",
    "OrderConfirmed": "Your order is confirmed",
    "OrderPaymentFailed": "We couldn't process your payment",
    "OrderCancelled": "Your order was cancelled",
    "PaymentCaptured": "Your payment was received",
    "PaymentFailed": "We couldn't take your payment",
    "DispatchConfirmed": "Your order has shipped",
    "DispatchFailed": "We couldn't ship your order",
}

BREAKER_OPEN = "Circuit breaker is open"
"""(capture) The error of event 50's row: the lookups before it opened user-client's breaker."""


def event_id(n: int) -> str:
    """CAPTURE.sh's `ev n`: the event id of record n."""
    return f"e0000000-0000-4000-8000-{n:012d}"


@dataclass(frozen=True, slots=True)
class SentEmail:
    """A `sent_email` row, less what varies by run: `id`, `body` and the timestamps
    (`sent_at` is set when `sent`, `failed_at` when `failed`)."""

    source_event_id: str
    event_type: str
    reason: str | None
    recipient_type: str
    """`email`, `customer` or `order`: what the event names the recipient by."""
    recipient_key: str
    customer_id: str | None
    order_id: str | None
    subject: str
    status: str
    """`sent`, `unresolved` or `failed` (`pending` only while in flight)."""
    error: str | None
    recipient_email: str | None


@dataclass(frozen=True, slots=True)
class Scenario:
    """One record CAPTURE.sh publishes, and what notification-service does with it."""

    topic: str
    key: str
    value: str | None
    """The record's value exactly as published; None for the null value."""
    comment: str
    """CAPTURE.sh's comment beside it (or what the line plainly does)."""
    row: SentEmail | None = None
    """The `sent_email` row it makes, if any."""
    dead_lettered: bool = False
    traceparent: str | None = None
    """The `traceparent` header it carries, if any."""

    @property
    def event_id(self) -> str | None:
        """The envelope's `eventId`; None when the value is no envelope."""
        return envelope_field(self.value, "eventId")

    @property
    def event_type(self) -> str | None:
        """The envelope's `eventType`; None when the value is no envelope."""
        return envelope_field(self.value, "eventType")

    @property
    def raw_value(self) -> str | None:
        """The value when it is no envelope (`{not json`, or None for the null value)."""
        return self.value if self.event_id is None else None


def envelope_field(value: str | None, name: str) -> str | None:
    """A string field of the envelope in a record's `value`; None when the value is
    no envelope (None, not JSON, not an object) or the field is no string."""
    if value is None:
        return None
    try:
        document = json.loads(value)
    except ValueError:
        return None
    field = document.get(name) if isinstance(document, dict) else None
    return field if isinstance(field, str) else None


def envelope(key: str, n: int, event_type: str, payload: str) -> str:
    """CAPTURE.sh's `env_`: the envelope of record n, correlated by the record's key."""
    return (
        f'{{"eventId":"{event_id(n)}","eventType":"{event_type}",'
        f'"timestamp":"2026-11-10T12:00:00Z","source":"capture",'
        f'"correlationId":"{key}","payload":{payload}}}'
    )


def order_payload(order: str, customer: str, extra: str = "") -> str:
    """CAPTURE.sh's `oc`: an order event's payload."""
    return f'{{"orderId":"{order}","customerId":"{customer}",{TIMESTAMP}{extra}}}'


def row(
    n: int,
    event_type: str,
    recipient_type: str,
    recipient_key: str,
    customer_id: str | None,
    order_id: str | None,
    recipient_email: str | None,
    *,
    reason: str | None = None,
    status: str = "sent",
    error: str | None = None,
) -> SentEmail:
    """The row event n makes; its subject by event type."""
    return SentEmail(
        source_event_id=event_id(n),
        event_type=event_type,
        reason=reason,
        recipient_type=recipient_type,
        recipient_key=recipient_key,
        customer_id=customer_id,
        order_id=order_id,
        subject=SUBJECTS[event_type],
        status=status,
        error=error,
        recipient_email=recipient_email,
    )


def _user_events() -> list[Scenario]:
    registered = f'{{"userId":"{U_OK}","email":"{ADA}"}}'
    return [
        Scenario(
            "user-events",
            U_OK,
            envelope(U_OK, 1, "UserRegistered", registered),
            "welcome email",
            row(1, "UserRegistered", "email", ADA, U_OK, None, ADA),
            traceparent=TRACEPARENT,
        ),
        Scenario(
            "user-events",
            U_OK,
            envelope(U_OK, 1, "UserRegistered", registered),
            "duplicate eventId",
        ),
        Scenario(
            "user-events",
            U_OK,
            envelope(U_OK, 2, "UserDeleted", f'{{"userId":"{U_OK}"}}'),
            "unrelated type",
        ),
        Scenario("user-events", U_OK, "{not json", "undecodable envelope", dead_lettered=True),
        Scenario(
            "user-events",
            U_OK,
            envelope(U_OK, 3, "UserRegistered", f'{{"userId":"{U_OK}"}}'),
            "undecodable payload",
            dead_lettered=True,
        ),
        Scenario("user-events", U_OK, None, "a null value (null.marker; no row, no dead letter)"),
    ]


def _order_events() -> list[Scenario]:
    def cancelled(n: int, reason: str | None, extra: str, comment: str) -> Scenario:
        return Scenario(
            "order-events",
            O_CUST,
            envelope(O_CUST, n, "OrderCancelled", order_payload(O_CUST, U_OK, extra)),
            comment,
            row(n, "OrderCancelled", "customer", U_OK, U_OK, O_CUST, ADA, reason=reason),
        )

    def actor(kind: str, actor_id: str) -> str:
        return f',"actor":{{"type":"{kind}","id":"{actor_id}"}}'

    return [
        Scenario(
            "order-events",
            O_CUST,
            envelope(O_CUST, 10, "OrderConfirmed", order_payload(O_CUST, U_OK)),
            "order confirmed",
            row(10, "OrderConfirmed", "customer", U_OK, U_OK, O_CUST, ADA),
            traceparent=TRACEPARENT,
        ),
        Scenario(
            "order-events",
            O_CUST,
            envelope(
                O_CUST,
                11,
                "OrderPaymentFailed",
                order_payload(O_CUST, U_OK, ',"reason":"capture_failed"'),
            ),
            "order payment failed",
            row(
                11,
                "OrderPaymentFailed",
                "customer",
                U_OK,
                U_OK,
                O_CUST,
                ADA,
                reason="capture_failed",
            ),
        ),
        cancelled(
            12, "customer", ',"reason":"customer"' + actor("customer", U_OK), "cancel: customer"
        ),
        cancelled(
            13,
            "auth_expired",
            ',"reason":"auth_expired"' + actor("system", "payment-service"),
            "cancel: auth_expired",
        ),
        cancelled(
            14, "stale", ',"reason":"stale"' + actor("system", "order-sweeper"), "cancel: stale"
        ),
        cancelled(
            15,
            "operator",
            ',"reason":"operator"' + actor("operator", "dev-operator"),
            "cancel: operator",
        ),
        cancelled(16, None, "", "legacy: no reason/actor"),
        cancelled(17, "meteor", ',"reason":"meteor"', "unknown reason"),
        Scenario(
            "order-events",
            O_GUEST,
            envelope(O_GUEST, 18, "OrderConfirmed", order_payload(O_GUEST, U_GONE)),
            "guest fallback",
            row(18, "OrderConfirmed", "customer", U_GONE, U_GONE, O_GUEST, GUEST),
        ),
        Scenario(
            "order-events",
            O_NOGUEST,
            envelope(O_NOGUEST, 19, "OrderConfirmed", order_payload(O_NOGUEST, U_GONE)),
            "unresolved",
            row(
                19,
                "OrderConfirmed",
                "customer",
                U_GONE,
                U_GONE,
                O_NOGUEST,
                None,
                status="unresolved",
                error=f"unknown_customer:{U_GONE}",  # (capture)
            ),
        ),
        Scenario(
            "order-events",
            O_GUEST,
            envelope(O_GUEST, 20, "OrderConfirmed", order_payload(O_GUEST, "not-a-uuid")),
            "user 400 -> guest",
            row(20, "OrderConfirmed", "customer", "not-a-uuid", "not-a-uuid", O_GUEST, GUEST),
        ),
        Scenario(
            "order-events",
            O_CUST,
            envelope(O_CUST, 21, "OrderCreated", order_payload(O_CUST, U_OK)),
            "unrelated type",
        ),
        Scenario(
            "order-events",
            O_CUST,
            envelope(O_CUST, 22, "OrderConfirmed", f'{{"orderId":"{O_CUST}"}}'),
            "undecodable payload",
            dead_lettered=True,
        ),
    ]


def _payment_events() -> list[Scenario]:
    def captured(order: str, cents: int) -> str:
        return f'{{"orderId":"{order}","amountCents":{cents},{TIMESTAMP}}}'

    failed = (
        f'{{"orderId":"{O_CUST}","paymentId":"{event_id(99)}","amountCents":4999,'
        f'"reason":"capture_failed",{TIMESTAMP}}}'
    )
    return [
        Scenario(
            "payment-events",
            O_CUST,
            envelope(O_CUST, 30, "PaymentCaptured", captured(O_CUST, 4999)),
            "payment captured",
            row(30, "PaymentCaptured", "order", O_CUST, U_OK, O_CUST, ADA),
            traceparent=TRACEPARENT,
        ),
        Scenario(
            "payment-events",
            O_CUST,
            envelope(O_CUST, 31, "PaymentFailed", failed),
            "payment failed",
            row(31, "PaymentFailed", "order", O_CUST, U_OK, O_CUST, ADA, reason="capture_failed"),
        ),
        Scenario(
            "payment-events",
            O_GONE,
            envelope(O_GONE, 32, "PaymentCaptured", captured(O_GONE, 100)),
            "unknown order",
            row(
                32,
                "PaymentCaptured",
                "order",
                O_GONE,
                None,
                O_GONE,
                None,
                status="unresolved",
                error=f"unknown_order:{O_GONE}",  # (capture)
            ),
        ),
        Scenario(
            "payment-events",
            O_GUEST,
            envelope(O_GUEST, 33, "PaymentCaptured", captured(O_GUEST, 2500)),
            "guest via order",
            row(33, "PaymentCaptured", "order", O_GUEST, U_GONE, O_GUEST, GUEST),
        ),
        Scenario(
            "payment-events",
            O_CUST,
            envelope(O_CUST, 34, "PaymentAuthorized", f'{{"orderId":"{O_CUST}"}}'),
            "unrelated type",
        ),
    ]


ITEMS = (
    '[{"sku":"SKU-0042","productName":"Espresso cup","quantity":2,"unitPriceCents":1250},'
    '{"sku":"SKU-0007","productName":"Grinder \\"Pro\\" é","quantity":1,"unitPriceCents":8999}]'
)
"""CAPTURE.sh's dispatched items (a quoted, non-ASCII product name among them)."""


def _fulfilment_events() -> list[Scenario]:
    return [
        Scenario(
            "fulfilment-events",
            O_GUEST,
            envelope(
                O_GUEST,
                40,
                "DispatchConfirmed",
                f'{{"orderId":"{O_GUEST}","trackingNo":"TRK-123456789","items":{ITEMS}}}',
            ),
            "dispatch confirmed (guest, via the order)",
            row(40, "DispatchConfirmed", "order", O_GUEST, U_GONE, O_GUEST, GUEST),
            traceparent=TRACEPARENT,
        ),
        Scenario(
            "fulfilment-events",
            O_CUST,
            envelope(
                O_CUST,
                41,
                "DispatchFailed",
                f'{{"orderId":"{O_CUST}","reason":"carrier_unavailable"}}',
            ),
            "dispatch failed",
            row(
                41,
                "DispatchFailed",
                "order",
                O_CUST,
                U_OK,
                O_CUST,
                ADA,
                reason="carrier_unavailable",
            ),
        ),
        Scenario(
            "fulfilment-events",
            O_CUST,
            envelope(
                O_CUST, 42, "DispatchConfirmed", f'{{"orderId":"{O_CUST}","trackingNo":"TRK-1"}}'
            ),
            "no items: undecodable",
            dead_lettered=True,
        ),
        Scenario(
            "fulfilment-events",
            O_NOGUEST,
            envelope(
                O_NOGUEST, 43, "DispatchFailed", f'{{"orderId":"{O_NOGUEST}","reason":"lost"}}'
            ),
            "unresolved",
            row(
                43,
                "DispatchFailed",
                "order",
                O_NOGUEST,
                None,  # (capture): not the order's customer, U_GONE, who has no email
                O_NOGUEST,
                None,
                reason="lost",
                status="unresolved",
                error=f"unknown_customer:{U_GONE}",  # (capture)
            ),
        ),
    ]


def _flaky_lookup() -> list[Scenario]:
    """CAPTURE.sh step 6, last: a user lookup that always fails opens the breaker."""
    return [
        Scenario(
            "order-events",
            U_FLAKY,
            envelope(U_FLAKY, 50, "OrderConfirmed", order_payload(O_CUST, U_FLAKY)),
            "transient lookup failure: it opens user-client's breaker",
            row(
                50,
                "OrderConfirmed",
                "customer",
                U_FLAKY,
                U_FLAKY,
                O_CUST,
                None,
                status="failed",
                error=BREAKER_OPEN,
            ),
            dead_lettered=True,
            traceparent=TRACEPARENT,
        ),
    ]


SCENARIOS: tuple[Scenario, ...] = (
    *_user_events(),
    *_order_events(),
    *_payment_events(),
    *_fulfilment_events(),
    *_flaky_lookup(),
)
"""Every record CAPTURE.sh publishes, in order."""


def expected_rows() -> tuple[SentEmail, ...]:
    """The `sent_email` rows the scenarios make, in publishing order."""
    return tuple(scenario.row for scenario in SCENARIOS if scenario.row is not None)


def expected_dead_letters(topic: str) -> tuple[Scenario, ...]:
    """The scenarios dead-lettered from input `topic`, in order (one partition each)."""
    return tuple(s for s in SCENARIOS if s.topic == topic and s.dead_lettered)
