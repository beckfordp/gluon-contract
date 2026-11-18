# Plan — notification-service user-events checks, written red (gluon RPN-10)

The contract of notification-service's `user-events` consumer as a check group,
`checks/test_notification_user_events.py`: six checks, one per record the
capture publishes (`notification_scenarios._user_events()`), each red against
notification-service-rs (no Kafka consumer yet) for one stated reason, and
reported PENDING (`pend`) by `scripts/verify-check-group.sh`.

Agreed with the owner 2026-11-17. Tasks marked **(gluon)** are made in gluon
directly (it doesn't use conductor); the rest are this repo's, one commit each.

**Done when** gluon `bin/verify-complete-RPN-10.sh` prints all PASS; its core:

    scripts/verify-check-group.sh checks/test_notification_user_events.py \
        --service notification-service --expect-red "not yet implemented"

## Decisions (2026-11-17, owner)
- **Runs.** The 14-minute done script runs again only when every phase is done;
  in between, the targeted tests and the group itself.
- **PENDING vs FAIL** (in the harness: `gluon_contract.pending`, `check_report`,
  `verify-check-group.sh --expect-red`). PENDING: the check has all the contract information it
  needs and fails only because the Rust side isn't built. FAIL: anything else
  (a regression, or contract information missing).
- **The discriminator.** Each check waits (one shared deadline for the group)
  until consumer group `notification-service-user-events`
  (`kafka/consumer-groups.txt`) has committed past its record. If the group
  never appeared: "not yet implemented" (PENDING). If it exists but didn't
  commit past the record: "not consumed" (FAIL). If consumed but wrong: the
  check's own assertion (FAIL). Kafka coordinator errors while waiting are
  "not yet", so nothing errors.
- **Stick to the contract.** Rows are compared on the scenario table's
  `SentEmail` fields only; gaps go to gluon `TECHNICAL_DEBT.md`.
- **Known duplication is left and flagged** in gluon `TECHNICAL_DEBT.md`
  (`TD-S<n>`, the sandbox's own list), e.g. `test_probe.py`'s `wait_until` and
  `lookups` stay where they are.
- **No `bin/sandbox-save`** until the owner says so (it cleans build output).
  The sandbox-only libz-sys 1.1.31 in user-service-rs's `Cargo.lock` is never
  committed; it is reverted before a save.

## The six checks (publishing order)
| # | Record (CAPTURE.sh) | Once consumed |
|---|---|---|
| 1 | `UserRegistered` e…001 (traceparent) | one row, the table's `SentEmail`; `sent_at` set; no `GET /users/…` |
| 2 | the same eventId again | still exactly one row for e…001 |
| 3 | `UserDeleted` e…002 | no row, no dead letter |
| 4 | `{not json` | on `user-events-dlq` unchanged (key, value, no headers); no row |
| 5 | `UserRegistered` e…003, no `email` | on `user-events-dlq` unchanged; no row |
| 6 | null value | no row, no dead letter; the replay leaves exactly #1's row and #4/#5's dead letters |

A module fixture clears `sent_email` first (the REST group's seed leaves
e…001's row), then replays the six records with their captured keys and headers.

## Phase 0: Acceptance first
- [x] 0.1 **(gluon)** `bin/verify-complete-RPN-10.sh`, RPN-5's shape; run once, red (9 of 12 FAIL)
- [x] 0.2 **(gluon)** `TECHNICAL_DEBT.md`: the sandbox's own list, TD-S1…TD-S10
- [x] 0.3 **(gluon)** shellcheck in the sandbox: `bin/sandbox-setup` step `shellcheck`
      (Ubuntu's .deb, unpacked without root; the apt download shared with `vim` as
      `apt_unpack`); `verify-complete-RPN-10.sh` shellcheck-clean

## Phase 1: Shared harness machinery (TDD)
- [x] 1.1 `KafkaBroker.produce` returns the record's offset; `KafkaBroker.has_group(group)`
      (`tests/integration/test_kafka_broker.py`)
- [x] 1.2 `NOT_YET_IMPLEMENTED = "not yet implemented"`, defined once; `check_report`
      classifies a failure carrying it as pending (`tests/unit/test_check_report.py`)
- [x] 1.3 `notification_scenarios.scenarios(topic)` (unit test)
- [x] 1.4 `sent_email.rows(connection, ...)`, the reader beside `insert` (integration test)
- [x] 1.5 `gluon_contract/consumption.py`: replay a topic's scenarios (offsets back),
      wait until committed past an offset against a shared deadline, with the
      discriminator; unit tests (fake broker and clock) for its three outcomes,
      one integration test (real broker: no consumer, a consumer that never commits,
      one that does; `tests/integration/test_consumption_broker.py`)
- [x] 1.6 `scripts/ci.sh` green (409 passed, coverage 95.46%)

## Phase 2: The group, written red
- [x] 2.1 `checks/test_notification_user_events.py`: `service("notification-service")`,
      the fixture, the six checks, each with a `Source:` paragraph citing the capture;
      rows judged by `notification_capture.row_differences`, the capture check's own
      rule, extracted so both use it
- [x] 2.2 README names the group; `scripts/ci.sh` green (412 passed, coverage 95.54%)
- [x] 2.3 `verify-check-group.sh ... --expect-red "not yet implemented"` passes (6 pend, ~1 min)

## Phase 3: Each notification-service group judged by `verify-check-group.sh`
Replanned 2026-11-17 (owner, option a): the PENDING mechanism is the harness's
`scripts/verify-check-group.sh --expect-red`, already the done criterion; gluon
`bin/verify-port` stays unchanged (no PENDING there: a whole notification-service
run says FAIL, C1 NOT MET, until the consumer is built, which may follow in this
session and removes the ambiguity).
- [x] 3.1 **(gluon)** `bin/verify-complete-RPN-10.sh`: the REST group still green with
      `verify-check-group.sh --expect-green` (24/24) replaces the `verify-port`
      notification-service and `verify-port-test.sh` criteria; shellcheck-clean

## Phase 4: Done
- [x] 4.1 Archive the track (`conductor/archive/notification-user-events/`)
- [x] 4.2 **(gluon)** every shell script changed in RPN-10 shellcheck-clean (`-x`):
      `bin/verify-complete-RPN-10.sh`, the only one
- [x] 4.3 **(gluon)** `bin/verify-complete-RPN-10.sh` all PASS, 11/11 in 13 min (run once, at the end:
      ~14 min), shown to the owner
