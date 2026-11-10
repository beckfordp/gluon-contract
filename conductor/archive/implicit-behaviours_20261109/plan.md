# Plan — RUST-1.9

## Phase 1: Traces (with RUST-3.2)
- [x] Task: checks — unmatched path span has no status code; CORS preflight not traced; only 5xx marks a span as error `96165bf` (green against the Rust build after RUST-3.2)

## Phase 2: The list
- [x] Task: checks for the behaviours found in Rust Spikes 3–6 (Java UUID parsing, metrics and log behaviours, HEAD/404 under /docs, event source, metrics scope), each seen red against an older build `b4efc91`, `97529f1`, `314b5ee`
- [x] Task: `docs/implicit-behaviours.md`, every item found in Rust Spikes 2–6 `2a1e865`
- [x] Task: `scripts/verify-implicit-behaviours.sh` — PASS (`--run`: 81 checks) `2a1e865`
