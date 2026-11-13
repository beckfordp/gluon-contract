# Plan — ns-rest_20261113: notification-service's REST check group (gluon RPN-4)

**Goal:** notification-service's first contract check group — `GET /emails`,
health, CORS, unknown paths — written here and seen failing against the
walking skeleton (notification-service-rs, RPN-2) for the stated reason: the
skeleton has no `/emails` route, so every `/emails` and CORS check gets a 404.
The session that turns it green is notification-service-rs's, later.

**Done when:** gluon `bin/verify-complete-RPN-4.sh` is green. It is red now
and is the acceptance test for this track; its criteria are the ones agreed
on 2026-11-13:
1. `scripts/ci.sh` green, including the seed unit test
   `test_the_seed_reproduces_every_captured_emails_answer`
2. `checks/test_notification_rest.py` against the skeleton: exactly the checks named
   below, every one failing (not erroring) with a 404 in its failure
   *(2026-11-13, option a: no green checks; health, readiness, HEAD and the
   unknown path stay with RPN-2's tests, re-run here as regression)*
3. selection by service: a notification-service run collects only
   `test_notification_rest.py`; a user-service run collects none of it
4. user-service unchanged: `bin/verify-rust-spike --only build contract`
   prints `ok   contract: 128/128 green`
5. `docs/implicit-behaviours.md` has N3–N8, each naming its check, and a
   not-checked entry for the order of `/emails` rows with equal `created_at`
6. README no longer says the notification-service run "deselects them all"
7. this plan archived (`conductor/archive/*/plan.md` naming RPN-4)
8. tests/contract and notification-service-rs have nothing uncommitted

**Decisions (2026-11-13):**
- Scope: the harness side only. notification-service-rs doesn't change.
- Seed data: the capture's own rows (`db/sent-email.jsonl`) inserted into
  `sent_email` through the `db` fixture; the module clears the table first.
  Nothing can create rows through the API until the consumers exist
  (RPN-10 on). Expected answers are the capture's `http/emails-*.txt`.
  Checked while planning: those rows, filtered and newest first, reproduce all
  13 captured `/emails` bodies exactly.
- No schema check in this group (it gets its own, as user-service's
  RUST-1.5 did). No `cluster` marker (seeding needs the database).
- Module `checks/test_notification_rest.py`, track script
  `scripts/verify-notification-rest-group.sh` *(2026-11-13: renamed from
  `test_ns_rest.py` and `verify-ns-rest.sh`, at the user's request: the
  names say the service; the track id stays `ns-rest_20261113`, as its
  commits record it)*.
- Each check asserts status first, so a failure shows the status it got.

Status: `[ ]` to do, `[~]` in progress, `[x]` done (with its commit).

## Phase 1: Baseline and seed data [checkpoint: 0668990]

- [x] Task: Baseline (2026-11-13) `b5bac5d`
    - [x] `bin/verify-complete-RPN-4.sh` run and red: 3 of 11 PASS (ci.sh,
          the skeleton builds, user-service 128/128); FAIL: no
          `tests/unit/test_sent_email.py`; no `checks/test_notification_rest.py`;
          notification-service collects nothing; no N3–N8 or `/emails` ties
          entry; README still "deselects them all"; no archived track; this
          plan uncommitted. Setup added on the way: the AsyncAPI HTML is built
          before ci.sh (as RPN-0), since ci.sh's cluster-mode integration test
          needs it once user-service-rs is built
    - [x] notification-service-rs `cargo build --locked` → `target/debug/notification-service`
    - [x] The harness's notification-service world up and down cleanly, every
          check deselected: `scripts/verify-multi-service-harness.sh --skip-ci
          --skip-contract` PASS 20/20 (a run with every check deselected never
          starts the harness, so RPN-3's script is the baseline)
- [x] Task: Seed helper `src/gluon_contract/sent_email.py` (TDD) `6371a86`
    - [x] Red: `tests/unit/test_sent_email.py` — the captured rows parse
          (20, typed, instants with their offsets);
          `test_the_seed_reproduces_every_captured_emails_answer` (each
          captured `/emails` body equals the rows captured before it, filtered
          as its query says, newest first, rendered as the capture renders them).
          Seen failing: no module
    - [x] Green: load the capture's rows; insert them through a connection.
          Two mutations of `existing_at` caught (1 and 8 failures)
    - [x] Integration test `tests/integration/test_sent_email_seed.py`: rows
          inserted into a throwaway Postgres with the capture's `db/schema.sql`
          (the Scala table's pg_dump, loaded with psql; no cross-repo read in
          CI) read back unchanged. A mutation of `insert` caught
    - [x] `scripts/ci.sh` green: 273 passed, coverage 94.45% (`sent_email` 97%)
- [x] Task: Check support for notification-service `2833e91`
    - [x] `assert_same` / `assert_text_error` reading notification-service's
          capture, added beside user-service's (those modules unchanged).
          *(2026-11-13: in `src/gluon_contract/expect.py`, not
          `checks/support.py`: unit-tested directly and under the coverage
          gate, importable by both services' checks. pytest doesn't rewrite
          asserts outside test modules, so each failure spells out capture,
          expected and actual, status first.)* `tests/unit/test_expect.py`:
          red (no module), green; two mutations caught (status and body
          comparisons skipped). user-service's copies in `checks/test_rest.py`
          stay for the later DRY refactor
    - [x] `scripts/ci.sh` green: 282 passed, coverage 94.53% (`expect` 100%)
- [x] Task: `scripts/verify-notification-rest-group.sh`, Phase 1 part *(2026-11-13: moved here
      from Phase 3; workflow: "written with the track and extended each phase")*
    - [x] CI; the seed seen from outside: the capture's rows inserted into a
          throwaway Postgres with the capture's `db/schema.sql`, dumped as
          CAPTURE.sh did (psql, `row_to_json`, UTC): byte for byte
          `db/sent-email.jsonl`; the seed reproducing each captured answer
    - [x] Failure path proven once in a copy (dump ordered by id: FAIL, exit 1)
- [x] Task: Conductor - User Manual Verification 'Phase 1' (Protocol in workflow.md)
    - [x] `scripts/verify-notification-rest-group.sh` PASS 18/18; confirmed by the user 2026-11-13

## Phase 2: The REST group, `checks/test_notification_rest.py` [checkpoint: 174f473]

Marked `pytest.mark.service("notification-service")`. A `seeded` fixture clears
`sent_email` and seeds the 19 rows that existed when `emails-all` was captured
*(2026-11-13: per check, through the existing `db` fixture, not once per module)*.
Each docstring names its capture file. Expected against the skeleton in
brackets; a check whose names change updates `bin/verify-complete-RPN-4.sh`
in the same change.

- [x] Task: `GET /emails` [red: 404] `238cad7`
    - [x] `test_emails_lists_every_email_newest_first` — `emails-all`
    - [x] `test_emails_filters_as_captured` [customer, order, both, guest-order,
          no-match] — `emails-customer`, `-order`, `-both`, `-guest-order`, `-none`
    - [x] `test_an_empty_filter_matches_nothing` (N3) — `emails-empty-param`
    - [x] `test_filters_compare_text_not_uuids` (N4) — `emails-not-uuid`
    - [x] `test_a_repeated_filter_is_a_plain_text_400` (N5) — `emails-repeated-param`
    - [x] `test_a_trailing_slash_is_the_same_resource` (N6) — `emails-trailing-slash`
    - [x] `test_unknown_query_parameters_are_ignored` (N7) — `emails-unknown-param`
    - [x] `test_a_traceparent_does_not_change_the_answer` — `emails-traceparent`
    - [x] `test_a_failed_send_shows_when_and_why` (adds row 50, removes it) —
          `emails-after-flaky`
    - [x] `test_emails_with_another_method_is_405` [POST, DELETE, HEAD] —
          `emails-post`, `-delete`, `-head`
    - [x] Against the skeleton: 16 of 16 red, 0 errors, each
          `expected <status> …, got 404 text/plain; charset=UTF-8; body 'Not found'`
          (HEAD: body ''). Seeding through the `db` fixture (per check: delete,
          then the 19 rows), so no check depends on another's leftovers
- [x] Task: CORS [red: 404] `2f4a7d3`
    - [x] `test_a_cors_preflight_is_answered_as_captured` — `cors-preflight`
    - [x] `test_a_preflight_for_a_disallowed_header_gets_no_allow_headers` (N8) —
          `cors-preflight-bad-header`
    - [x] `test_a_cross_origin_request_gets_allow_origin` — `cors-simple`
    - [x] `assert_same_cors` in `src/gluon_contract/expect.py` (TDD): status,
          then every CORS header as a set, absent where the capture has none;
          `CORS_HEADERS` shared (user-service's copy stays for the DRY
          refactor). Mutations: status skipped, caught; `Vary` ignored, NOT
          caught at first, so `test_vary_is_compared_too` added, now caught
    - [x] Against the skeleton: 3 of 3 red, 0 errors, each
          `expected 200, got 404; body 'Not found'`
- [x] Task: Regression testing: health, readiness, HEAD, unknown path (built and
      verified in RPN-2) *(2026-11-13: regression only, at the user's direction)*
    - [x] notification-service-rs `cargo test --locked --test health --test readiness`:
          7 passed (health 200 no body/Content-Type, HEAD 405, unknown path
          404, SIGTERM, bad config, readiness follows stopped Postgres, paused
          Postgres 503 within 3 s)
    - [x] notification-service-rs `scripts/verify-skeleton.sh --skip-ci`: PASS 8/8
          (health exchanges match the capture, sent_email DDL matches)
- [x] Task: `scripts/verify-check-group.sh` takes the service *(2026-11-13)* `5b0c674`
    - [x] `--service` (default user-service): the Rust repo, binary and capture
          it names; `--service notification-service` passes to pytest.
          user-service's `verify-*-group.sh` unchanged in use: `verify-rest-group.sh
          --skip-ci --expect-green` output identical before and after (28/28, 41 green)
    - [x] `--expect-red PATTERN` (beside `--expect-green`): every check fails, not
          errors or skips, each failure holding PATTERN; read from a junit report.
          Failure paths: `got 500` against the skeleton (every check named),
          and user-service's green group (each "passes")
    - [x] `scripts/verify-notification-rest-group.sh` runs the group through it: every check
          red, each with a 404 (section 4: 13 checks name their source; all 19
          red with 'got 404'). Failure path proven once in a copy (`got 500`)
- [x] Task: The run against the skeleton
    - [x] 19 red, 0 green, 0 errors; every failure shows the 404
          (`verify-check-group.sh … --expect-red "got 404"`: all 19 red)
    - [x] `mypy checks` and ruff clean
- [x] Task: Conductor - User Manual Verification 'Phase 2' (Protocol in workflow.md)
    - [x] `scripts/verify-notification-rest-group.sh` PASS 19/19; approved by the user 2026-11-13

## Phase 3: Records, verification, close [checkpoint: d80757e]

- [x] Task: `docs/implicit-behaviours.md` `b27e51e`
    - [x] N3 empty filter matches nothing; N4 filters are text, not UUIDs;
          N5 repeated filter is a plain-text 400 the spec doesn't list;
          N6 `/emails/` is `/emails`; N7 unknown parameters ignored;
          N8 a preflight for a disallowed header is 200 with no `Allow-*`
    - [x] Not checked: the order of rows with equal `created_at` (none in the
          capture; the Scala tie-break is production code)
    - [x] `scripts/verify-implicit-behaviours.sh`: PASS 36/36 (the six new checks found)
- [x] Task: Docs — README (status, "More than one service"), tech-stack layout `5cd0c58`
- [x] Task: `scripts/verify-notification-rest-group.sh`, Phase 3 part: selection by service `9fa78b4`
    - [x] Section 5: a notification-service run collects only
          `checks/test_notification_rest.py` (19 checks); a user-service run
          none of it (128 checks from 10 modules). Failure path proven once in
          a copy (another module expected: FAIL, exit 1)
- [x] Task: Conductor - User Manual Verification 'Phase 3' (Protocol in workflow.md)
    - [x] `scripts/verify-notification-rest-group.sh` PASS 21/21; approved by the user 2026-11-13
- [x] Task: Review; archive this track; `bin/verify-complete-RPN-4.sh` green
      (it runs `bin/sandbox-save`); archive downloaded
    - [x] Review (2026-11-13): expectations only from the capture, `openapi.yaml`
          and the Scala suites; every check names its source; failures spelled
          out, status first; every new code path's mutation caught (one gap,
          `Vary`, found and closed). Risk: the group is seen red only, until
          the Rust session implements `/emails` and CORS and the Scala service
          confirms it on the laptop. Debt proposals: gluon `TECHNICAL_DEBT.md`
          (TD-33–TD-42)
    - [x] Archived to `conductor/archive/ns-rest_20261113/`
    - [ ] `bin/verify-complete-RPN-4.sh` green and `bin/sandbox-save`'s archive
          downloaded (recorded by the done script's run, not in this file)
