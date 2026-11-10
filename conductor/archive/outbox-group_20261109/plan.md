# Plan — RUST-1.6: Outbox and envelope group

## Phase 1
- [x] Task: write failing helper tests (registry, Debezium routing) `97fa818`
- [x] Task: implement the helpers (`registry.py`, `routing.py`) `325f283`
- [x] Task: the checks, each with a Source: line; run against the Rust build and record `e9362ef`
  — Rust build: 1 green (refused signup writes nothing), 4 red until RUST-3.1
- [x] Task: verify script `scripts/verify-outbox-group.sh` `e9362ef`
