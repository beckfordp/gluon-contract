# Plan — RUST-6.5: Probe group

## Phase 1
- [x] Task: write failing tests for `probe.py` (the env contract) `6d871c8`
- [x] Task: implement `probe.py` and the `probe` fixture `27c93da`
- [x] Task: `checks/test_probe.py`; run (red: no probe yet) `27c93da` — red against the placeholder; 2/10 after RUST-6.2, 5/10 after 6.3, 10/10 after 6.4
- [x] Task: `scripts/verify-probe-group.sh`; green once RUST-6.2–6.4 land `fd3fdef` — PASS (12 checks)
