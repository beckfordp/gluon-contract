# Plan — RUST-1.5: Schema and stored-format group

## Phase 1: Schema snapshot
- [x] Task: write failing tests (pure diff; snapshot of two databases built from the same and from different SQL)
- [x] Task: implement `gluon_contract/schema.py`

## Phase 2: The checks
- [x] Task: `checks/test_schema.py`, every check with a `Source:` line; run against the Rust build and record
- [x] Task: `scripts/verify-schema-group.sh`
