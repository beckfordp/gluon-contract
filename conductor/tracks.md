# Project Tracks

This file tracks all major tracks for the project.

---

## Tracks

- [ ] **Track: TD-46, TD-41: verify scripts into CI, every citation checked**
  *Link: [./tracks/retire-scripts_20261113/](./tracks/retire-scripts_20261113/)*

---

## Backlog

Title-only placeholders for future tracks — not yet detailed (no spec/plan, no linked
folder), so `/conductor:implement` cannot pick these up by accident. Source of truth for
scope: gluon `plans/rust-port/user-service/plan.md` (ADR 0028). One track per PLAN item, worked in order,
each ending with a review. When ready, run `/conductor:newTrack <title>`.

- GitHub Actions green on ubuntu + macOS (unparked 2026-11-11: work is on main only, red CI hides real failures): Ubuntu `CONTRACT_PG_BIN`, gluon files for 3 unit tests, uv-managed Python on macOS
- RUST-5.4: (laptop) Cluster mode with the Rust service deployed — REST group against gluon-local, the real `user-events` topic
