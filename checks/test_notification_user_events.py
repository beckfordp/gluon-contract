# SPDX-License-Identifier: MIT

"""notification-service's user-events consumer (gluon RPN-10; ADR 0029).

Expectations come from the reference, never the implementation under test: the
capture `contracts/notification-service/20261111` (`CAPTURE.sh`'s user-events records,
`db/sent-email.jsonl`, `kafka/user-events-dlq.txt`, `kafka/consumer-groups.txt`,
`requests.jsonl`), as the scenario table `gluon_contract.notification_scenarios` holds
it, and gluon's documented contracts (docs/system-design.md "Envelope" and
"Consume-time lookups (ADM-3)"; ADR 0010, ADR 0025).

The records carry the capture's own ids (event ids, the user U_OK), not fresh
throwaway ones: the rows are judged against the capture's by `source_event_id`. That
is safe because isolated mode starts an empty Postgres and broker for every session,
and these checks don't run in cluster mode.

The six records are replayed once, in the capture's order, after `sent_email` is
emptied (the REST group's seed leaves the capture's rows, the welcome email's among
them). Each check first waits until the consumer group has committed past its record
(`gluon_contract.consumption`): the Scala consumer commits only after handling, so the
outcome is there to look at, and a check expecting nothing can't pass before anything
happened. No consumer at all fails saying "not yet implemented" (PENDING).
"""

from typing import Any

import psycopg
import pytest

from gluon_contract.consumption import Replay, replay
from gluon_contract.harness import Harness
from gluon_contract.kafka import KafkaBroker, Record
from gluon_contract.notification_capture import row_differences
from gluon_contract.notification_scenarios import (
    event_id,
    expected_dead_letters,
    scenarios,
)
from gluon_contract.postgres import connect
from gluon_contract.sent_email import rows

pytestmark = pytest.mark.service("notification-service")
"""notification-service's contract: deselected in a run for another service (RPN-3)."""

TOPIC = "user-events"
GROUP = "notification-service-user-events"
"""The consumer group, as the capture's kafka/consumer-groups.txt names it."""
DLQ = f"{TOPIC}-dlq"

type Db = psycopg.Connection[tuple[Any, ...]]


@pytest.fixture(scope="module")
def replayed(harness: Harness) -> Replay:
    """`sent_email` emptied, then the capture's user-events records published, once."""
    assert harness.kafka is not None, "notification-service's harness starts a broker"
    with connect(harness.postgres.endpoint) as connection:
        connection.execute("delete from sent_email")
    return replay(harness.kafka, TOPIC, GROUP, scenarios(TOPIC))


def broker(harness: Harness) -> KafkaBroker:
    """The service's broker."""
    assert harness.kafka is not None
    return harness.kafka


def dead_letters(harness: Harness) -> list[Record]:
    """Everything on user-events-dlq now, read to its end: once a record is committed its
    dead letter, if any, is already there, so there is nothing to wait for."""
    return broker(harness).records_now(DLQ)


def user_lookups(harness: Harness) -> list[str]:
    """The paths of every `GET /users/…` the user-service stub has had."""
    stub = harness.stubs["user-service"]
    return [r.path for r in stub.requests() if r.path.startswith("/users/")]


def test_a_user_registered_event_sends_the_welcome_email(
    harness: Harness, replayed: Replay, db: Db
) -> None:
    """One `sent_email` row, as the table says: "Welcome to gshop" to the event's email
    (recipient type `email`, customer the user), status `sent` with `sent_at` set. The
    recipient is in the payload, so no user lookup is made.

    Source: capture CAPTURE.sh, db/sent-email.jsonl and ./requests.jsonl (user-events'
    "welcome email"; its row; no GET /users/ before the order events);
    docs/system-design.md "Consume-time lookups (ADM-3)" (a lookup only for an event
    without an email).
    """
    record = replayed.consumed(0)
    expected = record.scenario.row
    assert expected is not None
    found = rows(db, source_event_id=event_id(1))
    assert len(found) == 1, f"{len(found)} rows for the welcome event: {found}"
    assert row_differences(expected, found[0]) == []
    assert user_lookups(harness) == []


def test_a_repeated_event_id_sends_no_second_email(replayed: Replay, db: Db) -> None:
    """The same UserRegistered delivered again (same eventId): still one row for it; the
    eventId is the idempotency key.

    Source: capture CAPTURE.sh and db/sent-email.jsonl (user-events' "duplicate eventId";
    one row for e…001).
    """
    replayed.consumed(1)
    found = rows(db, source_event_id=event_id(1))
    assert len(found) == 1, f"{len(found)} rows for the repeated event: {found}"


def test_an_unrelated_event_type_is_skipped(harness: Harness, replayed: Replay, db: Db) -> None:
    """UserDeleted has no route: no row, nothing dead-lettered; the consumer moves on.

    Source: capture CAPTURE.sh, db/sent-email.jsonl and kafka/user-events-dlq.txt
    (user-events' "unrelated type"; neither holds e…002); docs/system-design.md
    "Envelope" (an eventType a consumer doesn't handle is skipped silently).
    """
    replayed.consumed(2)
    assert rows(db, source_event_id=event_id(2)) == []
    skipped = scenarios(TOPIC)[2].value
    assert [r for r in dead_letters(harness) if r.value == skipped] == []


def test_an_undecodable_envelope_is_dead_lettered_unchanged(
    harness: Harness, replayed: Replay, db: Db
) -> None:
    """`{not json` goes to user-events-dlq once, as it came: its key, its value, no
    headers. It makes no row.

    Source: capture CAPTURE.sh and kafka/user-events-dlq.txt (user-events' "undecodable
    envelope"; the first dead letter: the key, `{not json`, NO_HEADERS); ADR 0010
    (bounded retry, then the topic's DLQ).
    """
    record = replayed.consumed(3)
    sent = record.scenario
    found = [r for r in dead_letters(harness) if r.value == sent.value]
    assert [(r.key, r.value, r.headers) for r in found] == [(sent.key, sent.value, {})]
    assert [row.source_event_id for row in rows(db)] == [event_id(1)]


def test_an_undecodable_payload_is_dead_lettered_unchanged(
    harness: Harness, replayed: Replay, db: Db
) -> None:
    """A UserRegistered without `email` goes to user-events-dlq once, the whole envelope
    as it came, no headers. It makes no row.

    Source: capture CAPTURE.sh and kafka/user-events-dlq.txt (user-events' "undecodable
    payload"; the second dead letter: e…003's envelope, NO_HEADERS); ADR 0010.
    """
    record = replayed.consumed(4)
    sent = record.scenario
    found = [r for r in dead_letters(harness) if r.value == sent.value]
    assert [(r.key, r.value, r.headers) for r in found] == [(sent.key, sent.value, {})]
    assert rows(db, source_event_id=event_id(3)) == []


def test_a_null_value_is_skipped(harness: Harness, replayed: Replay, db: Db) -> None:
    """A record with no value: no row, no dead letter. Once it is consumed, the whole
    replay has made exactly the table's rows and dead letters, and the group has
    committed all six records.

    Source: capture CAPTURE.sh, kafka/user-events-dlq.txt, consumer-groups.txt and
    db/sent-email.jsonl (user-events' null.marker record; notification-service-user-events
    at offset 6 of 6).
    """
    replayed.consumed(5)
    expected = [(s.key, s.value) for s in expected_dead_letters(TOPIC)]
    assert [(r.key, r.value) for r in dead_letters(harness)] == expected
    made = [row.source_event_id for row in rows(db)]
    assert made == [s.row.source_event_id for s in scenarios(TOPIC) if s.row is not None]
