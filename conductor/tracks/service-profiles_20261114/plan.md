# Plan — Per-service profiles, then notification health checks (TD-44, TD-42)

Phase verification: the spec's acceptance commands, run and shown. No verify script
(TD-46 rule).

## Phase 0: Baseline
- [x] Task: Record the baseline
    - [x] `scripts/ci.sh` test count and run time
    - [x] `bin/verify-port user-service --only build contract` (expect 128/128)
    - [x] The notification REST group against notification-service-rs
          (`verify-check-group.sh --service notification-service`)
    - *Baseline 2026-11-14 (laptop, HEAD `2df21fb`): `ci.sh` 362 passed, 95.16%, 122 s
      (run at `45edbe6`; only conductor files changed since). `verify-port user-service
      --only build contract` PASS, 128/128. Notification REST group: 0 green, 19 red
      (`/emails` is RPN-5's).*

## Phase 1: Per-service profiles (TD-44.1)
- [ ] Task: The run's service is required
    - [ ] Red: unit tests show that, without CONTRACT_SERVICE, `load_config` raises a
          ConfigError naming KNOWN_SERVICES, `run_service` fails the same way, and the
          pytest plugin's usage-error message says so
    - [ ] Drop `DEFAULT_SERVICE`; the `--service` help no longer names a default
    - [ ] Callers pass it: `ci.sh`, `verify-check-group.sh`, the `pytest_plugin` tests,
          and gluon `bin/verify-port` (a gluon change, needs approval)
- [ ] Task: Capture helpers need the service
    - [ ] Remove the default and let mypy and the tests drive the changes
    - [ ] `ServiceProfile.capture` (→ `latest_capture`); the helpers take the service;
          every `checks/test_user_*.py` passes its `SERVICE` constant
- [ ] Task: The variable prefix lives in the profile
    - [ ] `ServiceProfile.prefix`, defaulting to `variable_prefix(name)`; `env_contract`
          reads it
    - [ ] Unit test: a profile with an explicit prefix is honoured
- [ ] Task: Stubs answer from the profile
    - [ ] Red: `HttpStub(answers=...)` unit tests: an order-service stub answers 404 on
          `/users/x`, a user-service stub 200 with `user_body`; scripted behaviours
          unchanged
    - [ ] `ServiceProfile.stub`, a table from route to answer (user-service:
          `GET /users/{id}`)
    - [ ] The harness builds each called service's stub from its profile
    - [ ] `USER_PATH` and `user_body` move to the user-service profile
    - [ ] The probe checks stay green (they script the user stub)
- [ ] Task: Guard: a new service is one profile
    - [ ] Unit test with a made-up `cart-service` profile and a temporary capture: its
          capture, prefix, env and stub are all reached with no other edits
    - [ ] `tech-stack.md` Layout note
- [ ] Task: Conductor - User Manual Verification 'Phase 1' (Protocol in workflow.md):
      ci.sh, user-service 128/128, notification group as in the baseline

## Phase 2: Notification health checks (TD-42.1)
- [ ] Task: Health checks in `test_notification_rest.py`
    - [ ] Red: run the checks against a notification-service-rs build whose `/health`
          answers a wrong body (a temporary local patch, not committed); they fail,
          naming the capture
    - [ ] `/health` and `/health/ready`: 200, as captured
    - [ ] HEAD `/health`
    - [ ] The unknown path: a plain-text 404
    - [ ] Readiness: 503 with Postgres stopped, 200 once it's back
    - [ ] Written as in `test_user_rest.py`, using only the shared helpers in `expect`
          and `support` (the TD-34 guard)
    - [ ] Green against notification-service-rs, built here on the laptop
- [ ] Task: Green against Scala
    - [ ] `sbt -batch stage` in `services/notification-service`
    - [ ] Run the group with `verify-check-group.sh` against the staged
          `bin/notification-service`; record the results
- [ ] Task: notification-service-rs drops its health fixtures (its own repo and commit)
    - [ ] Remove the health test from `tests/capture.rs`, and `tests/fixtures/http/`
    - [ ] Narrow the `rust.md` §8 exception to `db/schema.sql`
    - [ ] Its `ci.sh` green
- [ ] Task: Tick TD-44.1 and TD-42.1 in gluon `TECHNICAL_DEBT.md` (needs approval)
- [ ] Task: Conductor - User Manual Verification 'Phase 2' (Protocol in workflow.md):
      both builds green, notification-service-rs ci.sh green
