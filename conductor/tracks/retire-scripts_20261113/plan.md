# Plan — retire-scripts (gluon TD-46, TD-41)

## Phase 1: Acceptance and coverage map [checkpoint: 1182b42]
- [x] Task: `scripts/verify-retire-scripts.sh`, red `4ba3dc0` — 33 of 38 failed: 14 present and self-named, check-group §1/§2, no `test_check_sources.py`, no rule; ci.sh green (290 passed, 94.52%)
  - [x] Checks: retired scripts gone; kept present + `bash -n` clean; no `git grep` hits outside `conductor/archive`; verify-check-group.sh has no §1/§2; rule in workflow.md; `scripts/ci.sh` green
  - [x] Run: red for the stated reasons
- [x] Task: Coverage map in this plan: each section of the 16 other `verify-*.sh` → named covering test / ci.sh step / verify-port step, or "keep: <reason>"
  - [x] Unmapped CI-runnable sections listed as Phase 2 tests (marked **gap**)

  Every script's "CI" section → `scripts/ci.sh` (verify-port `harness-ci`); every "group against the Rust build" → verify-port `contract` (all of `checks/`, `--probe-cmd` included). The rest:

  | Script § | Covered by |
  |---|---|
  | rest, schema, outbox, docs, telemetry, cdc-group: check-group §2 sources | **gap** → `tests/unit/test_check_sources.py` (TD-41) |
  | cdc-group: CDC jars present | harness config error (`test_config.py` `test_a_service_that_needs_a_broker_needs_the_kafka_jars`) |
  | probe-group §2 Source: lines | `test_check_sources.py` |
  | probe-stubs §2 | `tests/unit/test_http_stub.py`, `tests/integration/test_kafka_broker.py` |
  | isolated-runner §2 bad config | `test_pytest_plugin.py` `test_an_unusable_configuration_stops_the_run_with_every_problem`; `test_config.py` |
  | isolated-runner §3 live run (env, Postgres, OTLP, metrics, log) | `test_harness.py` `test_the_target_gets_exactly_the_env_contract`, `test_logs_spans_metrics_and_the_database_are_wired`; `test_postgres.py` (login, wrong password, logical WAL); `test_otlp_stub.py` (JSON, 415, 404) |
  | isolated-runner §4 teardown | `test_harness.py` `test_nothing_survives_a_run` |
  | isolated-runner §5 failed start | `test_harness.py` `test_a_failed_start_tears_everything_down`; `test_target.py` `test_a_target_that_exits_early_fails_with_its_output` |
  | isolated-runner §6 entry point, `--keep-artifacts` | `test_pytest_plugin.py` `test_a_check_gets_a_ready_harness_and_everything_stops`, `test_keep_artifacts_leaves_the_work_directory` |
  | isolated-runner §7 PROVENANCE | `test_contracts.py` `test_every_capture_in_this_repo_has_its_provenance` |
  | multi-service §2 env vs gluon-local values | **gap** → `test_env_contract.py`: names read from gluon `environments/local/<service>.values.yaml` (as `registry.py` reads gluon) |
  | multi-service §3 notification world | `test_harness.py` `test_notification_service_gets_a_broker_with_its_topics_and_a_stub_per_called_service`; migration is notification-service-rs's own tests |
  | multi-service §4 selection by service | `test_check_markers.py` `test_every_module_in_checks_is_marked_for_a_known_service`; `test_pytest_plugin.py` `test_service_selects_the_checks_marked_for_it`, `test_a_service_without_a_profile_stops_the_run_before_any_check`; `test_config.py` (no jars) |
  | multi-service §5 user-service unchanged | verify-port `contract` |
  | notification-rest-group §2 seed round trip | `tests/integration/test_sent_email_seed.py` |
  | notification-rest-group §3 reproduces answers | `test_sent_email.py` (`-k reproduces`) |
  | notification-rest-group §4 red on skeleton | one-off (RPN-4's state); `verify-check-group.sh --expect-red` stays for the next group |
  | notification-rest-group §5 selection | as multi-service §4 |
  | notification-capture | `test_notification_capture.py` `test_the_committed_capture_passes`; a new capture: `uv run python -m gluon_contract.notification_capture check DIR` |
  | portable-harness §1 owner helper | `test_owner_sh.py` |
  | portable-harness §1 no `stat -c`/`getent`/`/proc` in scripts | **gap** → unit test over `scripts/**/*.sh` (owner.sh excepted) |
  | portable-harness §1 openings, §3 every script | one-off: the scripts it ran are retired |
  | portable-harness §2 | integration tests (ci.sh); isolated-runner as above |
  | implicit-behaviours §1 every listed check exists | **gap** → unit test over `docs/implicit-behaviours.md` |
  | implicit-behaviours §2 `--run` | verify-port `contract` (superset) |

  Kept: `verify-check-group.sh` (§3 only: a tool for writing groups red then green), `verify-user-scala-confirmation.sh` (laptop B2: stages the Scala service), `verify-cluster-mode.sh` (RUST-5.4 open, laptop; its §2 is skipped silently in CI without the jars/build).
- [x] Task: Conductor - User Manual Verification 'Phase 1' (Protocol in workflow.md)

## Phase 2: Into CI (TDD) [checkpoint: eb1ddcb]
- [x] Task: `tests/unit/test_check_sources.py`: every check in `checks/test_*.py` has a `Source:` line; every capture file it names exists (TD-41.1) `49feb0d`
  - [x] Red: a mutation that cites a missing later name (`http/a.txt, missing.txt`) fails; also catch any real gap the old §2 missed — red: no module; real mutation `emails-delete.txt` → `emails-deleted.txt` (a later name) fails the guard; no real gaps
  - [x] Green: parser in `src/gluon_contract/` (service from module name), fix real gaps — `check_sources.py`, service from the module's marker (`check_markers`); 27 passed
- [x] Task: one test per unmapped CI-runnable section from the map (e.g. implicit-behaviours §1: every check `docs/implicit-behaviours.md` names exists), red then green `6fe7829` — `test_implicit_behaviours.py`; `test_owner_sh.py` no `stat -c`/`getent`/`/proc` outside owner.sh; `test_env_contract.py` vs gluon-local values; each red on a mutation. `verify-portable-harness.sh` deleted here (its own grep pattern was the only hit)
- [x] Task: `scripts/ci.sh` green, coverage ≥ 80% — 321 passed, 1 skipped (`test_cluster_mode`, no CDC jars here), 94.62%
- [x] Task: Conductor - User Manual Verification 'Phase 2' (Protocol in workflow.md)

## Phase 3: Retire
- [x] Task: `verify-check-group.sh` cut to §3 (header, usage, `--skip-ci` removed) `24f1058` — `test_user_schema.py --expect-green` PASS
- [x] Task: delete covered scripts (the 7 group wrappers + others the map covers) `6e35b31` — 13 (portable-harness in `6fe7829`)
- [x] Task: live references updated (README, tech-stack, docs/implicit-behaviours.md); archives untouched `30e76ee`
- [x] Task: Conductor - User Manual Verification 'Phase 3' (Protocol in workflow.md)

## Phase 4: Rule
- [ ] Task: `conductor/workflow.md` Phase Completion step 4: retirement rule (user-service-rs wording)
- [ ] Task: `verify-retire-scripts.sh` PASS; failure path proven on a copy
- [ ] Task: Conductor - User Manual Verification 'Phase 4' (Protocol in workflow.md)

At archive: `verify-retire-scripts.sh` deleted (per the rule). gluon follow-up: verify-port `CONTRACT_TRACK_SCRIPTS`, docs/ports table, docs/sandbox.md rule, TD-41/TD-46 ticks.

Risks: verify-port step 6 lists deleted scripts until the gluon follow-up lands (the tracks step goes red). Bigger scripts (isolated-runner, multi-service-harness, portable-harness) may hold live-run sections only integration tests can cover.
