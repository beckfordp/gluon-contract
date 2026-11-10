# Plan — RUST-1.3: REST group

## Phase 1: Helpers
- [x] Task: psycopg 3.3.7 and `http.client` recorded in the tech stack; dependency added
- [x] Task: write failing unit tests for `http`, `capture` and `formats`
- [x] Task: implement them

## Phase 2: The checks

*Against the Rust build on 2026-11-09 (only `/health`, readiness path `/health`): 1 green, 34 red, every red a 404 — the stated reason. Green is RUST-2.6's exit criterion (`scripts/verify-rest-group.sh --expect-green`).*

- [x] Task: `checks/test_rest.py` and its fixtures, every check with a `Source:` line
- [x] Task: run against the Rust build (today: `/health` only) and record the failures and their reasons
- [x] Task: `scripts/verify-rest-group.sh`
