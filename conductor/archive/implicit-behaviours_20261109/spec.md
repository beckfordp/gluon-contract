# Spec — RUST-1.9: Record implicit behaviours

## Overview
gluon PLAN.md RUST-1.9 (ADR 0028 decision 3). Behaviour the Scala service
has that no document states — found while porting — is recorded twice: as a
check in the harness naming its source (the capture, purerest/purekafka, the
Scala code), and in `docs/implicit-behaviours.md`, which says whether it is a
documentation gap and where it is raised (user-service OpenAPI descriptions —
laptop; gluon `system-design.md`). No behaviour changes. The track stays open
through Rust Spikes 3 and 4, collecting items as they are found.

## Functional Requirements
1. Every item found has a check (or says why it can't have one, e.g. a random
   flag that isn't contract) with a `Source:` line, first seen failing
   against a build without it.
2. `docs/implicit-behaviours.md`: one row per item — behaviour, source, check,
   contract or not, documentation gap and where raised.

## Acceptance Criteria
- `scripts/verify-implicit-behaviours.sh` PASS: CI green; every row of the
  list names a check that exists (or "no check" with a reason); the checks
  it names run green against the Rust build once Rust Spikes 3–4 are done.
