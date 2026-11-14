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

## Phase 1: Per-service profiles (TD-44.1) [checkpoint: ace4f77]
- [x] Task: The run's service is required 24c7867
    - [x] Red: unit tests show that, without CONTRACT_SERVICE, `load_config` raises a
          ConfigError naming KNOWN_SERVICES, `run_service` fails the same way, and the
          pytest plugin's usage-error message says so
    - [x] Drop `DEFAULT_SERVICE`; the `--service` help no longer names a default
    - [x] Callers pass it: `ci.sh`, `verify-check-group.sh`, the `pytest_plugin` tests,
          and gluon `bin/verify-port` (a gluon change, needs approval)
    - *Required only where it matters: a run collecting service-marked checks, or
      building a harness config. The harness's own tests name none. Gluon
      `bin/verify-port` and `docs/ports/user-service-verification.md` updated in the
      working tree, to commit at the phase check.*
- [x] Task: Capture helpers need the service 3e19dc3
    - [x] Remove the default and let mypy and the tests drive the changes
    - [x] `ServiceProfile.capture` (→ `latest_capture`); the helpers take the service;
          every `checks/test_user_*.py` passes its `SERVICE` constant
- [x] Task: The variable prefix lives in the profile 4ea17c2
    - [x] `ServiceProfile.prefix`, defaulting to `variable_prefix(name)`; `env_contract`
          reads it
    - [x] Unit test: a profile with an explicit prefix is honoured
- [x] Task: Stubs answer from the profile d71425c
    - [x] Red: `HttpStub(answers=...)` unit tests: an order-service stub answers 404 on
          `/users/x`, a user-service stub 200 with `user_body`; scripted behaviours
          unchanged
    - [x] `ServiceProfile.stub`, a table from route to answer (user-service:
          `GET /users/{id}`)
    - [x] The harness builds each called service's stub from its profile
    - [x] `USER_PATH` and `user_body` move to the user-service profile
    - [x] The probe checks stay green (they script the user stub)
    - *An answer is a function (path → JSON body, or None for 404) rather than a table:
      user-service's is `user_lookup`. Probe 10/10 against Rust.*
- [x] Task: Guard: a new service is one profile 2842248
    - [x] Unit test with a made-up `cart-service` profile and a temporary capture: its
          capture, prefix, env and stub are all reached with no other edits
    - [x] `tech-stack.md` Layout note
    - *Green on its first run, as a guard over the four tasks above should be.*
- [x] Task: Conductor - User Manual Verification 'Phase 1' (Protocol in workflow.md):
      ci.sh, user-service 128/128, notification group as in the baseline
    - *2026-11-14: ci.sh 373 passed, 95.23%. `verify-port user-service --only build
      contract` 128/128 (with gluon's `--service user-service`, working tree). Notification
      REST group 0 green, 19 red, as the baseline.*

## Phase 2: Notification health checks (TD-42.1) [checkpoint: 79283d2]
- [x] Task: Health checks in `test_notification_rest.py` f8bcc85
    - [x] Red: run the checks against a notification-service-rs build whose `/health`
          answers a wrong body (a temporary local patch, not committed); they fail,
          naming the capture
    - [x] `/health` and `/health/ready`: 200, as captured
    - [x] HEAD `/health`
    - [x] The unknown path: a plain-text 404
    - [x] Readiness: 503 with Postgres stopped, 200 once it's back
    - [x] Written as in `test_user_rest.py`, using only the shared helpers in `expect`
          and `support` (the TD-34 guard)
    - [x] Green against notification-service-rs, built here on the laptop
    - *Red 3/3 against a patched build (a body on /health, HEAD routed to GET, another
      404 text, readiness always 200; reverted): each new check red where its behaviour
      was broken. Green 3/3 against the real build: 5 green, the 19 /emails checks red as
      before (RPN-5). HEAD is a text/plain 405 without Allow, as the capture.*
- [x] Task: Green against Scala 7871f51
    - [x] `sbt -batch stage` in `services/notification-service`
    - [x] Run the group with `verify-check-group.sh` against the staged
          `bin/notification-service`; record the results
    - *2026-11-14, notification-service `b60d4d7`: 24/24 (the 5 new checks, and the 19
      `/emails` checks, against Scala). Run with pytest directly, as runbook B2 does:
      `verify-check-group.sh` builds only the Rust port. The first `sbt stage` hit
      TD-51 (`ClassNotFoundException: notificationservice.AsyncApiChannels$`); the
      retry passed, so TD-51 affects notification-service too. Health and HEAD now also
      compare `Content-Length`, as the Rust capture test did.*
- [x] Task: notification-service-rs drops its health fixtures (its own repo and commit) notification-service-rs bd7d8da
    - [x] Remove the health test from `tests/capture.rs`, and `tests/fixtures/http/`
    - [x] Narrow the `rust.md` §8 exception to `db/schema.sql`
    - [x] Its `ci.sh` green
    - *Also gone: `canon_exchange`, `Service::exchange` (only that test used them) and
      `.gitattributes` (it kept only those fixtures byte for byte).*
- [x] Task: Tick TD-44.1 and TD-42.1 in gluon `TECHNICAL_DEBT.md` (needs approval) gluon bd2bfdf
- [x] Task: Conductor - User Manual Verification 'Phase 2' (Protocol in workflow.md):
      both builds green, notification-service-rs ci.sh green
    - *2026-11-14: Rust 5 green, the 19 `/emails` checks red (RPN-5); Scala 24/24;
      notification-service-rs ci.sh green after `bd7d8da`; tests/contract ci.sh 373
      passed, 95.23%.*
