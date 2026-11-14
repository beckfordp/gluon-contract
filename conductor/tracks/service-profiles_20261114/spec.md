# Spec: Per-service profiles, then notification health checks (TD-44, TD-42)

## Overview
Per-service facts are spread through tests/contract. Capture helpers default to
user-service, there is `config.DEFAULT_SERVICE`, and `http_stub` answers only
user-service's `GET /users/{id}`. Adding cart-service would touch them all (TD-44).
Once that is fixed, notification-service's health checks move into the harness, so
the Scala service faces them too (TD-42).

## Functional Requirements
### Phase 1 — TD-44.1
- FR-1: `ServiceProfile` carries each service's capture (the latest dated directory
  under `contracts/<service>/`), its variable prefix, and how its stub answers when a
  check hasn't scripted it.
- FR-2: No user-service default anywhere.
  - `capture_file` and `load_exchange` take `service` with no default.
  - A run without `CONTRACT_SERVICE` or `--service` is a usage error that names the
    known services.
  - `DEFAULT_SERVICE` goes.
  - Every caller passes the service: the checks, `ci.sh`, `verify-check-group.sh`
    and gluon `bin/verify-port`.
- FR-3: `http_stub` is generic. Its answers come from the profile of the service it
  stands in for:
  - user-service: `GET /users/{id}` → 200 `{userId,email,createdAt}`
  - order-service: 404

  The scripted behaviours (Status, Delay, Hang, Reset) are unchanged.
- FR-4: A guard proves that adding a service is one profile plus its checks: a unit
  test with a made-up profile reaches its capture, prefix and stub without other
  edits.

### Phase 2 — TD-42.1
- FR-5: `test_notification_rest.py` gains these checks, compared against capture
  20261111:
  - `/health` and `/health/ready`: 200, with the captured headers and body
  - HEAD `/health`
  - the unknown path: a plain-text 404
  - readiness: 503 with Postgres stopped, 200 once it's back

  They are built on `expect` and `support`, as the user-service versions are.
- FR-6: In notification-service-rs, `tests/capture.rs`'s health test and
  `tests/fixtures/http/` go, and its `rust.md` §8 exception narrows to the schema
  fixture. This is its own commit, in that repo.

## Non-Functional Requirements
- Red first where behaviour changes: the FR-2 usage error, the FR-3 stub answers,
  and FR-5 against a build without the routes or with a wrong body.
- `scripts/ci.sh` green; coverage at least 80%.

## Acceptance Criteria
- user-service: `bin/verify-port user-service --only build contract` passes 128/128,
  before and after.
- The notification REST group, run with `verify-check-group.sh`, is green against
  notification-service-rs and against the staged Scala build (`sbt stage`, on the
  laptop).
- notification-service-rs `ci.sh` is green without the http fixtures.

## Out of Scope
- The paused-Postgres captures (`health-pg-paused`, `health-ready-pg-paused`): they
  have no user-service counterpart; a later TD item if wanted.
- notification-service-rs's schema fixture, which stays until a notification schema
  group exists.
- RPN-9's order-service stub answers beyond "no order".
