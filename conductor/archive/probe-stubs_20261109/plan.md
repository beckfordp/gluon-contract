# Plan — RUST-6.1: Probe stubs

## Phase 1
- [x] Task: write failing tests (HTTP stub behaviours; broker produce/read, outage and restart, committed offsets) `6868d5e`
- [x] Task: implement `http_stub.py`, `KafkaBroker`; fixtures `7e10eb8`
- [x] Task: `scripts/verify-probe-stubs.sh` — PASS (10 checks) `1572857`
