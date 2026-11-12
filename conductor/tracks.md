# Project Tracks

This file tracks all major tracks for the project.

---

## Tracks


---

## Backlog

Title-only placeholders for future tracks — not yet detailed (no spec/plan, no linked
folder), so `/conductor:implement` cannot pick these up by accident. Source of truth for
scope: gluon `PLAN.md` "Rust Spike" (ADR 0028). One track per PLAN item, worked in order,
each ending with a review. When ready, run `/conductor:newTrack <title>`.

- GitHub Actions green on ubuntu + macOS (unparked 2026-11-11: work is on main only, red CI hides real failures): Ubuntu `CONTRACT_PG_BIN`, gluon files for 3 unit tests, uv-managed Python on macOS
- RUST-5.4: (laptop) Cluster mode with the Rust service deployed — REST group against gluon-local, the real `user-events` topic
- Check the probe's lookup timeout by the order of events, not elapsed time:
  a lookup past `PROBE_LOOKUP_TIMEOUT` is abandoned and retried while the slow
  answer is still held (the timing check was removed 2026-11-12; see
  `docs/implicit-behaviours.md`, "Not checked, and why")
