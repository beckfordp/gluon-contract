# Project Tracks

This file tracks all major tracks for the project.

---

## Tracks

- [ ] **Track: One helper per job in tests/contract (TD-34, TD-35, TD-36, TD-45)**
  *Link: [./tracks/one-helper_20261114/](./tracks/one-helper_20261114/)*

---

## Backlog

Title-only placeholders for future tracks — not yet detailed (no spec/plan, no linked
folder), so `/conductor:implement` cannot pick these up by accident. Source of truth for
scope: gluon `plans/rust-port/user-service/plan.md` (ADR 0028),
`plans/rust-port/notification-service/plan.md` (ADR 0029) and `TECHNICAL_DEBT.md`.
One track per PLAN item (or TD group), worked in order, each ending with a review. For
an RPN item shared with notification-service-rs, this repo's track is the check group,
written red before the Rust track turns it green. When ready, run
`/conductor:newTrack <title>`.

RPN-4.1 tidy (laptop, before RPN-5):
- Per-service profiles, notification health checks (TD-44, then TD-42): one profile per service (capture, variable prefix, stubs), no user-service defaults; then `/health`, `/health/ready`, HEAD, unknown path, readiness with Postgres down in `test_notification_rest.py`, green against Rust and Scala, notification-service-rs's vendored `http/` fixtures retired
- Full failure reasons in check output (TD-40): `verify-check-group.sh` reads each outcome and message from the junit report

CI:
- GitHub Actions green on ubuntu + macOS (unparked 2026-11-11: work is on main only, red CI hides real failures): Ubuntu `CONTRACT_PG_BIN`, gluon files for 4 unit tests (incl. `test_env_contract`'s gluon-local values), uv-managed Python on macOS
- Shellcheck in CI (TD-38, this repo's part): `scripts/*.sh` linted by `ci.sh` and GitHub Actions; pinned shellcheck in gluon `bin/sandbox-setup`

notification-service check groups (sandbox, after RPN-8):
- RPN-9: Kafka fixtures — produce with key and headers (incl. null values), an order-service stub beside the user stub (a TD-44 profile stub), a DLQ reader, consumer-group offsets
- RPN-10: `user-events` checks red — welcome email, duplicate eventId, unrelated type, undecodable envelope and payload → DLQ, null value skipped
- RPN-11: audited-send checks red — claim, mark sent / failed / unresolved, no resend of sent or unresolved, pending/failed retried
- RPN-12: recipient-resolution checks red — customer, guest fallback, user 400 → guest, unknown customer, unknown order
- RPN-13: transient-lookup-failure checks red — HTTP retry inside processing retry, breaker opening, row failed, record dead-lettered
- RPN-14: `order-events` checks red — confirmed, payment failed, cancelled with each reason
- RPN-15: `payment-events` and `fulfilment-events` checks red — captured, failed, unknown order; dispatched, dispatch failed, missing items → DLQ
- RPN-16: notification traces checks red — consume span on `traceparent`, lookup client spans, `/emails` server span
- RPN-17: notification metrics checks red — HTTP server and client, email journey, event age, lag, DLQ, stream restarts, breaker
- RPN-18: notification logs checks red — field order, message catalogue, outcome fields
- RPN-19: notification OpenAPI checks red — `/emails` and health in tapir's shape, Swagger UI paths
- RPN-20: notification AsyncAPI checks red — JSON (receive channels, payload schemas) and HTML

Laptop:
- RUST-5.4: (laptop) Cluster mode with the Rust service deployed — REST group against gluon-local, the real `user-events` topic
