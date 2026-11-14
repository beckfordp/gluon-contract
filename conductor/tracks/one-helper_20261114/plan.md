# Plan — One helper per job in tests/contract (TD-34, TD-35, TD-36, TD-45)

Phase verification: each phase's walkthrough is the acceptance commands in spec.md,
run and shown. No `scripts/verify-<track>.sh` (spec decision; TD-46 rule).

## Phase 1: Baseline and shared check helpers (TD-34) [checkpoint: 3e23151]
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
- [x] Task: Conductor - User Manual Verification 'Baseline and shared check helpers' (Protocol in workflow.md)
    - ci.sh green; user-service contract run matches the baseline count
    - *2026-11-14 (prompting off, run not walked through): ci.sh PASS 337 passed 94.65%;
      verify-port contract 128/128 (= baseline); notification group 19 red with '404' (= baseline).*

## Phase 2: One Postgres connect, one sent-email parser (TD-35, TD-36) [checkpoint: 74adec8]
- [x] Task: `postgres.connect` (TD-35) f224c00
    - [x] Red: guard rule 2 in `test_shared_helpers.py`: ast finds `psycopg.connect(`
          calls in `src/` and `tests/`, allowed only inside `postgres.connect`. Fails
          on the 4 sites
    - [x] Red: an integration test (`tests/integration/test_postgres.py`) where
          `connect(endpoint)` and `connect(endpoint, database=...)` reach the
          throwaway cluster with autocommit
    - [x] Green: `connect` in `postgres.py`; `pytest_plugin.db`,
          `schema.create_reference` (endpoint from `connection.info` or passed in,
          whichever touches fewer callers), and the two integration tests use it
    - *2026-11-14: `create_reference` builds the endpoint from `connection.info` (no
      caller changes); `schema` reuses `postgres.Connection`. Guard covers `checks/`
      too. ci.sh 343 passed, 94.75%; schema 6/6.*
- [x] Task: `sent_email.parse_row` (TD-36) e2c1d0f
    - [x] Red: `tests/unit/test_sent_email.py`: `parse_row` returns a typed row, and
          raises on non-JSON and on a missing column. `parse_rows` keeps its
          line-numbered messages
    - [x] Green: `parse_row`; `parse_rows` uses it
    - [x] Red/Green: `check_sent_email` on `parse_row`, one Problem per bad line,
          compares typed rows (timestamps by set/null only, as today). The existing
          broken-copy cases in `test_notification_capture.py` pass unchanged; add a
          missing-column case
    - [x] `uv run python -m gluon_contract.notification_capture check` passes on the
          latest capture
    - *2026-11-14: messages are `line N: <why>` in both callers (`parse_rows` said
      `line N is not JSON`); blank lines skipped by both (`numbered_lines`); a non-object
      line is now its own problem. ci.sh 348 passed, 94.85%; capture check PASS (60 files).*
- [x] Task: Conductor - User Manual Verification 'One Postgres connect, one sent-email parser' (Protocol in workflow.md)
    - *2026-11-14 (prompting off): ci.sh PASS 348 passed 94.85%; verify-port contract 128/128
      (= baseline); notification group 19 red with '404' (= baseline); capture check PASS.*

## Phase 3: Kafka broker out of cdc.py (TD-45) [checkpoint: 4aea434]
- [x] Task: `processes.py` → `supervisor.py` `9d87f2f`, `f414b2d`
    - [x] `_Processes`/`_signal` moved, public: `Supervisor` (spawn, wait, logs, stop,
          `stop_all`), `signal_group`, `port_open`, `StackError`
    - *Decided 2026-11-14:* first named `java_processes` (`processes.py` clashed with
      `tests/integration/processes.py`); renamed `supervisor` at the user's request,
      named for its job, not its technology. The Java specifics (jar check, log4j,
      `java` command line) are `kafka.Jars`. `CdcError` renamed `StackError` (it is
      also the broker's and the cluster reader's).
- [x] Task: `kafka.py` `9d87f2f`, `f414b2d`
    - [x] `KafkaBroker`, `Record`, `broker_properties`, `CLUSTER_ID`, `KAFKA_VERSION`,
          `properties_text`, `Jars` in `kafka.py`; `DEBEZIUM_VERSION` and `cdc_home`
          in `cdc.py` (the install's directory names both versions; `cdc` already
          imports `kafka`, so no cycle)
    - [x] Imports updated in every caller; no re-export from `cdc`
    - [x] Tests: `test_kafka.py` (broker config, jars, properties),
          `test_supervisor.py`, `tests/integration/test_supervisor_process_group.py`;
          `cdc_home`'s test in `test_cdc.py`
    - [x] tech-stack.md Layout, dated note
    - [x] `cdc.py` holds Connect, Debezium and `cdc_home`; ci.sh green: 354 passed,
          95.02%
    - *Contract runs after `9d87f2f`: 2 of 3 FAIL in
      `test_readiness_is_503_while_postgres_is_down` (`pg_ctl: server does not shut
      down`). Not TD-45's: alternating runs (2026-11-14) failed the same way on
      `b3bb033`, before it. See the next task.*
- [x] Task: Readiness check's Postgres stop outlasts `pg_ctl`'s wait `07a86f6`
    - [x] Cause: a fast shutdown waits for each logical replication client to confirm
          the shutdown checkpoint, up to `wal_sender_timeout` (60 s), pg_ctl's own
          wait; Debezium confirms when it happens to (stops measured 4.5–208 s)
    - [x] Red first: `test_a_stop_does_not_wait_for_a_logical_replication_client`
          (`pg_recvlogical` frozen with SIGSTOP), 59.9 s, 3 of 3
    - [x] Fix: `ThrowawayPostgres.stop()` ends replication connections first
    - [x] Acceptance: ci.sh 355 passed, 95.03%; contract run 128/128 five times in a row
- [x] Task: Close the track
    - [x] Acceptance runs 1–5 from spec.md, against the baseline (2026-11-14):
          1. `ci.sh` PASS, 355 passed, 95.03% (baseline 325, 94.64%)
          2. user-service 128/128, five runs in a row (baseline 128/128)
          3. notification REST group: 19 red, each with '404' (as baseline)
          4. capture check PASS (60 files)
          5. one `psycopg.connect` call (`postgres.py`; the other matches are the
             guard's pattern and its tests); `class KafkaBroker` only in `kafka.py`
    - [x] gluon `TECHNICAL_DEBT.md`: TD-34.1, 35.1, 36.1, 45.1 ticked, TD-48 raised
          (`target.py`'s process handling into `Supervisor`), gluon `f6f0225`
- [x] Task: Conductor - User Manual Verification 'Kafka broker out of cdc.py' (Protocol in workflow.md)
    - Script-free (spec decision): the acceptance runs above, results shown to and
      approved by the user, 2026-11-14
