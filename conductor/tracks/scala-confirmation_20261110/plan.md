# Plan — RUST-5.0: Scala confirmation fixes

## Phase 1: Harness expectations
- [x] Task: metrics scope check excludes JVM runtime scopes `fc9300f`
  - [x] Red: confirm current check fails against Scala (already seen in RUST-5.0 run)
  - [x] Green: filter runtime scopes (named constant), docstring source; check passes against Scala
- [ ] Task: docs.yaml Content-Type is `application/yaml`
  - [ ] Red: confirm current check fails against Scala
  - [ ] Green: expectation + docstring; PROVENANCE.md note; check passes against Scala
- [ ] Task: `scripts/verify-scala-confirmation.sh`
  - [ ] Script runs harness (probe ignored) against staged Scala, ok/FAIL per group, summary, non-zero on failure
  - [ ] Failure path proven once on a broken copy
- [ ] Task: `scripts/ci.sh` green (unit tests, lint, mypy)
- [ ] Task: Conductor - User Manual Verification 'Phase 1' (Protocol in workflow.md)
