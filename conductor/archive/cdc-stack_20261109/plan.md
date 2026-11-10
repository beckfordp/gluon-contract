# Plan — RUST-1.8: Sandbox CDC stack

## Phase 1: the stack
- [x] Task: write failing tests (properties, connector overrides, missing jars; the stack end to end) `5f56d1f`
- [x] Task: implement `cdc.py`, the `cdc` fixture `b5e4162`

## Phase 2: the checks
- [x] Task: write failing routing test (`id` header) and `checks/test_cdc.py` `2d43a07`
- [x] Task: `id` in `routing.route`; group green against the Rust build `24ce7a6`
- [x] Task: `scripts/verify-cdc-group.sh` — PASS `1734ba1`
