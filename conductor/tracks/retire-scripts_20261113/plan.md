# Plan — retire-scripts (gluon TD-46, TD-41)

## Phase 1: Acceptance and coverage map
- [ ] Task: `scripts/verify-retire-scripts.sh`, red
  - [ ] Checks: retired scripts gone; kept present + `bash -n` clean; no `git grep` hits outside `conductor/archive`; verify-check-group.sh has no §1/§2; rule in workflow.md; `scripts/ci.sh` green
  - [ ] Run: red for the stated reasons
- [ ] Task: Coverage map in this plan: each section of the 18 other `verify-*.sh` → named covering test / ci.sh step / verify-port step, or "keep: <reason>"
  - [ ] Unmapped CI-runnable sections listed as Phase 2 tests
- [ ] Task: Conductor - User Manual Verification 'Phase 1' (Protocol in workflow.md)

## Phase 2: Into CI (TDD)
- [ ] Task: `tests/unit/test_check_sources.py`: every check in `checks/test_*.py` has a `Source:` line; every capture file it names exists (TD-41.1)
  - [ ] Red: a mutation that cites a missing later name (`http/a.txt, missing.txt`) fails; also catch any real gap the old §2 missed
  - [ ] Green: parser in `src/gluon_contract/` (service from module name), fix real gaps
- [ ] Task: one test per unmapped CI-runnable section from the map (e.g. implicit-behaviours §1: every check `docs/implicit-behaviours.md` names exists), red then green
- [ ] Task: `scripts/ci.sh` green, coverage ≥ 80%
- [ ] Task: Conductor - User Manual Verification 'Phase 2' (Protocol in workflow.md)

## Phase 3: Retire
- [ ] Task: `verify-check-group.sh` cut to §3 (header, usage, `--skip-ci` removed)
- [ ] Task: delete covered scripts (the 7 group wrappers + others the map covers)
- [ ] Task: live references updated (README, tech-stack, docs/implicit-behaviours.md); archives untouched
- [ ] Task: Conductor - User Manual Verification 'Phase 3' (Protocol in workflow.md)

## Phase 4: Rule
- [ ] Task: `conductor/workflow.md` Phase Completion step 4: retirement rule (user-service-rs wording)
- [ ] Task: `verify-retire-scripts.sh` PASS; failure path proven on a copy
- [ ] Task: Conductor - User Manual Verification 'Phase 4' (Protocol in workflow.md)

At archive: `verify-retire-scripts.sh` deleted (per the rule). gluon follow-up: verify-port `CONTRACT_TRACK_SCRIPTS`, docs/ports table, docs/sandbox.md rule, TD-41/TD-46 ticks.

Risks: verify-port step 6 lists deleted scripts until the gluon follow-up lands (the tracks step goes red). Bigger scripts (isolated-runner, multi-service-harness, portable-harness) may hold live-run sections only integration tests can cover.
