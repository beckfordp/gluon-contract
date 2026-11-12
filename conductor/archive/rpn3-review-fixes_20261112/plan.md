# Plan — fixes from the review of the multi-service harness (gluon PLAN.md RPN-3)

Track `rpn3-review-fixes_20261112`; spec: [`spec.md`](./spec.md).

## Phase 1: Review fixes [checkpoint: 099eb5a]

- [x] Task: R5, R11 — `HttpStub`'s unscripted answer is 404 for any path but
      `/users/{id}` (test first: `GET /orders/{id}` → 404); the verify script
      expects 404 from the order-service stub `3613ac7`
- [x] Task: R6 — the harness test asks the user-service stub for a real UUID,
      asserting 200 and its `userId` `1dbe706`
- [x] Task: R7 — the topic test: absent before `create_topics`, present after,
      a second call harmless; no partition claim `9ef6c8a`
- [x] Task: R8 — `create_topics` retries while the broker isn't ready,
      tolerates a topic that already exists, and raises `CdcError` naming the
      topics at its deadline (test first: a stopped broker, a short deadline) `64e3f74`
- [x] Task: R13 — the pytester default-run test runs with `--strict-markers` `a517c9d`
- [x] Task: R16, R18 — a unit test: every `checks/test_*.py` has a module-level
      service marker naming known services; verify section 4 reports each
      module's service instead of requiring `user-service` `66d5ee9`
- [x] Task: R10 — verify section 3 drops the circular broker comparison and
      says which results are seen from outside and which the harness reports `1cd7b6e`
- [x] Task: R9 — the archived plan's review section, corrected `0f28d04`
- [x] Task: R24 *(added 2026-11-12, the user's decision)* — drop the probe's slow-lookup timing check from user-service's contract (timing isn't contract), note why in `docs/implicit-behaviours.md`, and add a backlog item to check the retry by order of events `b261c29`
- [x] Task: Conductor - User Manual Verification 'Phase 1' (Protocol in workflow.md) `099eb5a`
