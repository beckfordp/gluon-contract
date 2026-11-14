# Plan — One helper per job in tests/contract (TD-34, TD-35, TD-36, TD-45)

Phase verification: each phase's walkthrough is the acceptance commands in spec.md,
run and shown. No `scripts/verify-<track>.sh` (spec decision; TD-46 rule).

## Phase 1: Baseline and shared check helpers (TD-34)
- [x] Task: Record the baseline
    - [x] `scripts/ci.sh` result and run time
    - [x] user-service contract run count (`bin/verify-port user-service --only build contract`)
    - [x] notification REST group outcome (`verify-check-group.sh ... --service notification-service --expect-red 404`)
    - [x] Record all three in this plan's notes
    - *Baseline 2026-11-14 (laptop, HEAD `b885488`): `ci.sh` PASS, 325 passed, coverage
      94.64%, 111 s. `verify-port user-service --only build contract` PASS, 128/128 (probe
      10, cdc 3, config 10, docs 22, logs 16, metrics 7, outbox 5, rest 41, schema 6,
      traces 8). Notification REST group: all 19 checks red, each with '404'.*
- [x] Task: Guard rule 1: no check module redefines a shared helper af92f04
    - [x] Red: `tests/unit/test_shared_helpers.py`. ast reads the top-level names of
          `checks/support.py` and `src/gluon_contract/expect.py`. Every other
          `checks/*.py` must not define them. Prove the failure path with an inline
          source. Run it: fails, naming `test_user_rest.py` and `test_user_schema.py`
    - [x] Put the ast reading in `src/gluon_contract/` (e.g. `check_sources` or a new
          `shared_names`) only if that makes it testable under the coverage gate;
          otherwise keep it in the test
- [x] Task: `test_user_rest.py` on `expect` and `support` af92f04
    - [x] Drop the local `assert_same`, `assert_text_error`, `TEXT_PLAIN`,
          `CORS_HEADERS`; use `expect` with `service="user-service"` (module-level
          `functools.partial` if every call would repeat it)
    - [x] CORS checks: `expect.assert_same_cors` where it compares the same things;
          otherwise `expect.CORS_HEADERS`. The body-is-empty assertion stays
    - [x] `new_email`, `PASSWORD`, `JSON` from support; `signup`/`login` over
          `support.post_credentials`
- [x] Task: `test_user_schema.py` on `support` af92f04
    - [x] `new_email`, `PASSWORD`, `JSON` from support; `post` over `support.post_credentials`
    - [x] Guard green; `mypy checks`, ruff clean
    - *2026-11-14: one commit for the three tasks (the guard is red until both modules
      move). Guard in `gluon_contract.shared_helpers` (under the coverage gate). Checks
      pass `service=SERVICE` to `expect` as notification's do, no partial. Red: 10
      redefinitions; green after. ci.sh 337 passed, 94.65%; rest 41/41, schema 6/6.*
- [ ] Task: Conductor - User Manual Verification 'Baseline and shared check helpers' (Protocol in workflow.md)
    - ci.sh green; user-service contract run matches the baseline count

## Phase 2: One Postgres connect, one sent-email parser (TD-35, TD-36)
- [ ] Task: `postgres.connect` (TD-35)
    - [ ] Red: guard rule 2 in `test_shared_helpers.py`: ast finds `psycopg.connect(`
          calls in `src/` and `tests/`, allowed only inside `postgres.connect`. Fails
          on the 4 sites
    - [ ] Red: an integration test (`tests/integration/test_postgres.py`) where
          `connect(endpoint)` and `connect(endpoint, database=...)` reach the
          throwaway cluster with autocommit
    - [ ] Green: `connect` in `postgres.py`; `pytest_plugin.db`,
          `schema.create_reference` (endpoint from `connection.info` or passed in,
          whichever touches fewer callers), and the two integration tests use it
- [ ] Task: `sent_email.parse_row` (TD-36)
    - [ ] Red: `tests/unit/test_sent_email.py`: `parse_row` returns a typed row, and
          raises on non-JSON and on a missing column. `parse_rows` keeps its
          line-numbered messages
    - [ ] Green: `parse_row`; `parse_rows` uses it
    - [ ] Red/Green: `check_sent_email` on `parse_row`, one Problem per bad line,
          compares typed rows (timestamps by set/null only, as today). The existing
          broken-copy cases in `test_notification_capture.py` pass unchanged; add a
          missing-column case
    - [ ] `uv run python -m gluon_contract.notification_capture check` passes on the
          latest capture
- [ ] Task: Conductor - User Manual Verification 'One Postgres connect, one sent-email parser' (Protocol in workflow.md)

## Phase 3: Kafka broker out of cdc.py (TD-45)
- [ ] Task: `processes.py`
    - [ ] Move `_Processes` and `_signal` (public names: `Processes`, `signal_group`,
          final names in task plan review); unit tests for any logic that has none
          today (`tests/unit/test_cdc.py` cases move with it)
- [ ] Task: `kafka.py`
    - [ ] Move `KafkaBroker`, `Record`, `broker_properties`, the Kafka constants, and
          whatever only the broker uses. `CdcError`, `HOST`, `cdc_home`,
          `_port_open`: to whichever module needs them, with no cycle (shared ones
          to `processes.py`). Decided in the task's plan review
    - [ ] Update imports in `harness`, `pytest_plugin`, `checks/test_probe.py`,
          `tests/integration/test_kafka_broker.py`, `tests/unit/test_cdc.py` (split
          into `test_kafka.py` if its cases are the broker's). No re-export
    - [ ] tech-stack.md Layout: `kafka`, `processes` with a dated note (TD-45)
    - [ ] `cdc.py` holds only Connect/Debezium; ci.sh green incl. `test_kafka_broker.py`
- [ ] Task: Close the track
    - [ ] Acceptance runs 1–5 from spec.md, results recorded here against the baseline
    - [ ] gluon `TECHNICAL_DEBT.md`: tick TD-34.1, 35.1, 36.1, 45.1 with dated notes
          (laptop file; separate gluon commit, shown for approval)
- [ ] Task: Conductor - User Manual Verification 'Kafka broker out of cdc.py' (Protocol in workflow.md)
