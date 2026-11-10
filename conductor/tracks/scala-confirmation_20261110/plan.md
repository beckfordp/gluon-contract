# Plan — RUST-5.0: Scala confirmation fixes

## Phase 1: Harness expectations [checkpoint: 675776f]
- [x] Task: metrics scope check excludes JVM runtime scopes `fc9300f`
  - [x] Red: confirm current check fails against Scala (already seen in RUST-5.0 run)
  - [x] Green: filter runtime scopes (named constant), docstring source; check passes against Scala
- [x] Task: docs.yaml Content-Type is `application/yaml` `6fa3fab`
  - [x] Red: confirm current check fails against Scala
  - [x] Green: expectation + docstring; PROVENANCE.md note; check passes against Scala
- [x] Task: `scripts/verify-scala-confirmation.sh` `97d32e1` — 119/119 green against Scala; failure path shown (charset expectation restored in a copy: exit 1, check named)
  - [x] Script runs harness (probe ignored) against staged Scala, ok/FAIL per group, summary, non-zero on failure
  - [x] Failure path proven once on a broken copy
- [x] Task: `scripts/ci.sh` green (unit tests, lint, mypy) — 161 passed, 92.7% coverage, once user-service-rs `4297774` dropped the charset (its `tests/integration/test_cluster_mode.py` runs the docs check against the Rust build); no code change
- [x] Task: Conductor - User Manual Verification 'Phase 1' (Protocol in workflow.md)
