# Spec — One helper per job in tests/contract (TD-34, TD-35, TD-36, TD-45)

## Overview
gluon RPN-4.1 tidy, harness side. Four TD items where the same job is written out
twice or more in tests/contract. Each job gets one helper, and a CI guard keeps it
that way. Refactor only: no check's expectation changes.

Decided 2026-11-14 (newTrack): TD-34 covers all duplicates, not just the comparisons;
TD-36 shares a per-line `parse_row`; TD-45 splits into `kafka.py` + `processes.py`;
acceptance is a CI guard plus the runs below, no track verify script.

## Functional requirements

**FR-1 — Response comparisons and check data shared (TD-34, all duplicates)**
- `checks/test_user_rest.py` drops its own `assert_same`, `assert_text_error`,
  `TEXT_PLAIN`, `CORS_HEADERS` and uses `gluon_contract.expect`
  (`service="user-service"`). CORS checks use `expect.assert_same_cors` or
  `expect.CORS_HEADERS`.
- `new_email`, `PASSWORD`, `JSON` and the credentials POST come from
  `checks/support.py` in every user check module (`test_user_rest.py`,
  `test_user_schema.py`). The local `call`/`signup`/`login`/`post` become thin
  wrappers over support's or are replaced by them.
- What a check asserts stays the same. Failure messages may grow (expect spells out
  expected and actual).

**FR-2 — One Postgres connect (TD-35)**
- `gluon_contract.postgres.connect(endpoint: PostgresEndpoint, *, database: str | None = None) -> Connection`
  (autocommit, the endpoint's login).
- Callers: `pytest_plugin.db`, `schema.create_reference` (takes the endpoint, or
  builds one from `connection.info`), `tests/integration/test_schema_snapshot.py`,
  `test_sent_email_seed.py`.

**FR-3 — One `sent-email.jsonl` parser (TD-36)**
- `sent_email.parse_row(line) -> SentEmailRow` raises `ValueError` (not JSON /
  missing column). `parse_rows` is built on it, with the same line-numbered messages.
- `notification_capture.check_sent_email` parses each line with `parse_row`, records
  a `Problem` per bad line and carries on. It compares typed rows against the
  scenario table.
- `notification_capture check` and `tests/unit/test_notification_capture.py`'s
  broken-copy cases still report what they report today (wording may change for a
  missing column).

**FR-4 — Kafka broker out of cdc.py (TD-45)**
- `gluon_contract/kafka.py`: `KafkaBroker`, `Record`, `broker_properties`,
  `KAFKA_VERSION`, `CLUSTER_ID` and what only the broker uses.
- `gluon_contract/processes.py`: `_Processes` and `_signal` (made public if they
  cross modules), used by both.
- `cdc.py` keeps only Connect/Debezium (`CdcStack`, worker/connector properties,
  `cdc_home` if Connect-specific, `CdcError`). Shared items go where both import them
  without a cycle.
- Callers (`harness`, `pytest_plugin`, `checks/test_probe.py`,
  `tests/integration/test_kafka_broker.py`, `tests/unit/test_cdc.py`) import from the
  new home. No re-export from `cdc`.
- tech-stack.md's Layout lists `kafka` and `processes` with a dated note.

**FR-5 — CI guard**
- A unit test (ast, as with `check_markers`) fails when:
  - a module in `checks/` defines a name (function or constant) that
    `checks/support.py` or `gluon_contract.expect` already defines;
  - `psycopg.connect` is called anywhere in `src/` or `tests/` outside
    `postgres.connect`.
- Its failure path is proven with a throwaway source in the test itself.

## Non-functional
- `scripts/ci.sh` green (format, lint, mypy strict, coverage >= 80%).
- No new dependencies.

## Acceptance criteria
1. `scripts/ci.sh` green, the new guard included.
2. user-service 128/128 green: `bin/verify-port user-service --only build contract`.
3. `scripts/verify-check-group.sh checks/test_notification_rest.py --service notification-service --expect-red 404`
   gives the same result as before.
4. `uv run python -m gluon_contract.notification_capture check` passes on the latest
   capture.
5. `git grep -n 'psycopg.connect('` finds one definition; `git grep -n 'class KafkaBroker'`
   finds it only in `kafka.py`.
6. gluon `TECHNICAL_DEBT.md`: TD-34, 35, 36, 45 ticked with dated notes.

No track verify script: these are covered by CI and the check runs (TD-46 rule).

## Out of scope
- Per-service profiles and `services.py` defaults (TD-44, Track B).
- Notification health checks (TD-42).
- Failure-message length in `verify-check-group.sh` (TD-40).
- Any change to what a check expects.
