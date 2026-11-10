# Plan — RUST-1.7: Traces, metrics, logs and config groups

## Phase 1
- [x] Task: write failing helper tests (metric shapes, traceparent, capture_file) `93ebfd6`
- [x] Task: implement the helpers (`metrics.py`, `formats.parse_traceparent`, `capture.capture_file`) `09e5c12`
- [x] Task: the checks, each with a Source: line; run against the Rust build and record `7c77469`
  — Rust build: config 6 of 7 green (service.name needs tracing); traces, metrics, logs red until RUST-3.2..3.4
- [x] Task: verify script `scripts/verify-telemetry-groups.sh` `7c77469`
