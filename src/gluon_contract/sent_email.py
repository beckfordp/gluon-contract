# SPDX-License-Identifier: MIT

"""notification-service's `sent_email` rows as its capture holds them, to seed a run (RPN-4).

Nothing creates rows through the API until the consumers exist (RPN-10 on), so the
REST checks insert the capture's own rows (`db/sent-email.jsonl`, a dump of the Scala
service's table) and expect the capture's answers (`http/emails-*.txt`). An answer
is only comparable with the rows that existed when it was recorded: `existing_at`.
"""

import json
from collections.abc import Iterable, Sequence
from dataclasses import astuple, dataclass, fields
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql

from gluon_contract.capture import capture_file
from gluon_contract.contracts import CONTRACTS_ROOT

SERVICE = "notification-service"
DUMP = "db/sent-email.jsonl"
TIMESTAMPS = frozenset({"created_at", "sent_at", "failed_at"})


@dataclass(frozen=True, slots=True)
class SentEmailRow:
    """One `sent_email` row, every column (the Scala service's V1 + V2)."""

    id: str
    source_event_id: str
    event_type: str
    reason: str | None
    recipient_type: str
    recipient_key: str
    customer_id: str | None
    order_id: str | None
    subject: str
    body: str
    status: str
    created_at: datetime
    sent_at: datetime | None
    failed_at: datetime | None
    error: str | None
    recipient_email: str | None


COLUMNS = tuple(field.name for field in fields(SentEmailRow))


def parse_rows(text: str) -> list[SentEmailRow]:
    """The rows of a `sent-email.jsonl` dump, in its order.

    Raises:
        ValueError: naming the line that isn't JSON or lacks a column.
    """
    rows = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            document: dict[str, Any] = json.loads(line)
        except ValueError as error:
            raise ValueError(f"line {number} is not JSON: {line[:80]!r}") from error
        missing = [column for column in COLUMNS if column not in document]
        if missing:
            raise ValueError(f"line {number}: missing column {', '.join(missing)}")
        values: dict[str, Any] = {
            column: (
                datetime.fromisoformat(document[column])
                if column in TIMESTAMPS and document[column] is not None
                else document[column]
            )
            for column in COLUMNS
        }
        rows.append(SentEmailRow(**values))
    return rows


def captured_rows(*, root: Path = CONTRACTS_ROOT) -> list[SentEmailRow]:
    """Every row of notification-service's latest capture."""
    path = capture_file(DUMP, service=SERVICE, root=root)
    return parse_rows(path.read_text(encoding="utf-8"))


def existing_at(rows: Iterable[SentEmailRow], date: str) -> list[SentEmailRow]:
    """The rows created before the second an HTTP `Date` header names had ended.

    `Date` has whole seconds, so a row created within that second counts as existing.
    """
    end = parsedate_to_datetime(date) + timedelta(seconds=1)
    return [row for row in rows if row.created_at < end]


def insert(connection: psycopg.Connection[Any], rows: Sequence[SentEmailRow]) -> None:
    """Inserts `rows` as they are, every column given."""
    statement = sql.SQL("insert into sent_email ({}) values ({})").format(
        sql.SQL(", ").join(map(sql.Identifier, COLUMNS)),
        sql.SQL(", ").join(sql.Placeholder() * len(COLUMNS)),
    )
    with connection.cursor() as cursor:
        cursor.executemany(statement, [astuple(row) for row in rows])
