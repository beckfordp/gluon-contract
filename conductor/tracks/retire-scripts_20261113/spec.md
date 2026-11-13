# Spec — retire-scripts: verify scripts into CI, every citation checked (gluon TD-46, TD-41)

## Overview
Every track left a `scripts/verify-<track>.sh` (19 now). Many repeat `ci.sh` or bin/verify-port's `contract` step. `verify-check-group.sh` §2 only checks the first `http/<name>.txt` a docstring cites (TD-41). Move what CI can run into CI, delete covered scripts, record the rule. Precedent: user-service-rs `retire-scripts_20261113`.

## Functional Requirements
- **FR1:** unit test (tests/unit) over every `checks/test_*.py`: each check has a `Source:` line; each capture file it names exists in the latest capture of that module's service (user-service, notification-service, probe). A bare name after `http/x.txt,` resolves under `http/`; other paths (e.g. `asyncapi-html/index.html`) resolve from the capture root (TD-41.1).
- **FR2:** `verify-check-group.sh` reduced to §3 (group against the Rust build, `--expect-green` / `--expect-red`), kept as a tool for writing groups. §1 and §2 removed.
- **FR3:** coverage map in plan.md: each section of every other `scripts/verify-*.sh` → covering unit/integration test, ci.sh step, or verify-port step. Covered → deleted. CI-runnable but uncovered → test written first (e.g. implicit-behaviours §1 "every listed check exists"). Not CI-runnable → kept, reason recorded.
- **FR4:** the 7 group wrappers (rest, schema, outbox, docs, telemetry, cdc, probe-group) deleted if the map covers them.
- **FR5:** `conductor/workflow.md` Phase Completion step 4 gets the retirement rule (same wording as user-service-rs).
- **FR6:** live references updated (README, tech-stack, docs/implicit-behaviours.md); archives untouched.

## Non-Functional Requirements
- `scripts/ci.sh` green, coverage ≥ 80%.
- New test fails on a missing later citation (proven on a mutation).

## Acceptance Criteria
`scripts/verify-retire-scripts.sh` PASS: deleted scripts gone; kept scripts present, `bash -n` clean; no `git grep` hits for deleted ones outside `conductor/archive`; rule in workflow.md; ci.sh green; failure path proven on a copy. Script itself retired at archive.

## Follow-ups (gluon root, after archive)
verify-port `CONTRACT_TRACK_SCRIPTS`, docs/ports/user-service-verification.md table, docs/sandbox.md rule, TD-41 + TD-46 ticks.

## Out of Scope
- user-service-rs scripts (done), notification-service-rs scripts (own track)
- TD-39 done-script library, TD-34/35
- full `bin/verify-port user-service` run
