# Spec — RUST-5.0: Scala confirmation fixes

## Overview
RUST-5.0 run (2026-11-10, laptop) against the staged Scala service: 117/119 green. Two failures are wrong harness expectations, not Scala defects.

## Functional Requirements
1. `test_config.py::test_the_service_name_scopes_the_metrics`: drop JVM runtime scopes (`cats.effect.runtime`, `io.opentelemetry.runtime-telemetry-java8`, both in capture `metrics.txt`) before asserting the remaining scopes == `{renamed-user-service}`. Docstring names the capture's runtime scopes as source.
2. `test_docs.py::test_the_openapi_spec_is_the_scala_one`: expect `Content-Type: application/yaml` (no charset). Docstring sources the RUST-5.0 run; drops the wrong tapir/UTF-8 claim.
3. `contracts/user-service/20261109/PROVENANCE.md` notes: GET `/docs/docs.yaml` headers not captured (`docs-yaml-headers.txt` is HEAD → 405, by design); Content-Type confirmed by RUST-5.0 run.
4. `scripts/verify-scala-confirmation.sh`: runs the harness against the staged Scala service (all groups bar probe), ok/FAIL summary, non-zero on failure.

## Non-Functional
No change to capture data files. Rust service will then fail the docs check until the user-service-rs track lands (expected, next track).

## Acceptance Criteria
- Harness against Scala: 119/119 green (incl. CDC 3/3).
- Unit tests / `scripts/ci.sh` green.

## Out of Scope
Rust Content-Type fix (user-service-rs track); gluon PLAN/findings/CHANGELOG ticks.
