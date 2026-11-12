# Plan — RPN-1: Capture into the harness

## Phase 1: The capture check [checkpoint: 8ef5946]
- [x] Task: failing unit tests `tests/unit/test_ns_capture.py` (exchanges incl. timed files and a
      non-exchange; OTLP `.json` round trip, differing spans, missing `.json`; `.jsonl`; DLQ
      records; rows: exact, another status, missing, extra; the table: 20 rows, 5 dead letters;
      the committed capture passes) — red for the stated reason (module missing) `91c931c`
- [x] Task: implement `ns_scenarios.py`, `ns_capture.py` — green, coverage `5bbe04a` (all but the committed-capture test, green with task 3; parse errors the checks don't define propagate, as for user-service)
- [x] Task: decode the OTLP exports (`decode-otlp`), commit the `.json` files; `CAPTURE.md` note `094ac68`
- [x] Task: `scripts/verify-ns-capture.sh` — PASS on the capture; FAIL naming the file on the
      three broken copies (http, otlp, row) `04fbd82`
- [x] Task: Conductor - User Manual Verification 'Phase 1' (Protocol in workflow.md) — scripts run in the sandbox; confirmation: bin/verify-complete-RPN-1.sh with the user

## Phase 2: Docs and completion
- [x] Task: `docs/implicit-behaviours.md` notification-service N1; README / tech-stack layout `5110333`
- [x] Task: `scripts/ci.sh` — exit 0: 210 passed, 1 skipped (test_cluster_mode: needs a built user-service-rs, as at baseline), coverage 94.01%
- [x] Task: gluon `bin/verify-complete-RPN-1.sh` — PASS 11/11 with the user, 2026-11-11 16:40 (run 20261111-163737); it saved gluon-sandbox-20261111-164050.tar.gz
- [x] Task: Conductor - User Manual Verification 'Phase 2' (Protocol in workflow.md) — the user's go-ahead and the completion run above

## Phase: Review Fixes
- [x] Task: Apply review suggestions `cc7e51b` (module docstring says what raises; no `Any` in `_base64_ids_to_hex`)
- [x] Task: Apply the conductor:review fixes `11a6ff0` (S2 constant mappings; T1 `short_envelope`; T2 exact messages; spec note)

## Review

- Reviewed 2026-11-11 (conductor:review, with the user): plan compliance yes (FR1-FR5 met;
  ci.sh green; verify-ns-capture.sh PASS on the capture and FAIL naming the file on the three
  broken copies; bin/verify-complete-RPN-1.sh at the end of the session). Deviations, agreed and
  now in spec.md: the error design (only what the checks define is a problem; anything else
  raises, as for user-service) and the table's exact `value`/`traceparent`. Style pass
  (python.md: no `Any`, no `type: ignore`, no broad `except`, frozen data, docstrings). Applied
  `11a6ff0`: S2 `SUBJECTS`/`TIMESTAMP_SET_BY_STATUS` as `Mapping`; T1 test helper renamed
  `short_envelope`; T2 exact messages for extra and duplicate rows. Left: S1 (rows compared as
  raw dicts), S3 (checks and I/O in one module, as `capture.py`). Tests: 50, ns_capture 99%
  (only the `python -m` line uncovered), ns_scenarios 100%; ci.sh 210 passed, 1 skipped (as at
  baseline), 94.01%. No blocking findings.
