# Spec — RPN-1: Capture into the harness

## Overview
gluon PLAN.md "Rust Port — notification-service", session RPN-1 (ADR 0029).
The capture `contracts/notification-service/20261111` (laptop, committed) is
the reference for the port. user-service's capture was only checked by being
used; this one gets a check of its own, and a scenario table the consumer
checks reuse (RPN-10 on).

## Functional Requirements
1. `src/gluon_contract/ns_scenarios.py` (pure data): `CAPTURE.sh`'s stub
   fixtures (users, orders) and one `Scenario` per record it publishes, in
   order (29: topic, key, event id and type, or the raw value when it is no
   envelope; the `CAPTURE.sh` comment; the expected `sent_email` row or none;
   dead-lettered or not). 20 rows; dead letters: user-events `{not json` and
   event 3, order-events 22 and 50, fulfilment-events 42. What no comment
   states (subjects, `error` texts, `customer_id` of an unresolved order
   lookup) is taken from the capture and marked so.
2. `src/gluon_contract/ns_capture.py`: checks, each a pure function returning
   problems (`file` relative to the capture, message with expected and
   actual), reusing `capture.parse_exchange`, `otlp.decode_traces`,
   `cluster.parse_console_line`:
   - every `http/*.txt` parses as an exchange; the timed health files
     (`CAPTURE.sh` step 9) end with curl's `elapsed=`/`curl_exit=` trailer and
     hold a response, or nothing with curl's timeout (exit 28)
   - every `otlp/*.pb` decodes, has a `.json` beside it, and the `.json`
     (OTLP/JSON) decodes to the same spans; no `.json` without a `.pb`
   - every `.jsonl` line is JSON
   - each `kafka/<topic>-dlq.txt` holds exactly the expected records, in
     order (key; event id, or the raw value)
   - `db/sent-email.jsonl` is exactly the table's rows, by `source_event_id`
     (all columns but `id`, `body` and the timestamps; `sent_at`/`failed_at`
     set as the status says)
   A thin reader runs them over a capture directory; `python -m
   gluon_contract.ns_capture check [DIR]` (default: the latest
   notification-service capture) prints `ok`/`FAIL <file>: …`, then `PASS` or
   `FAIL` and exits 1; `decode-otlp [DIR]` writes each `.pb`'s `.json`
   (OTLP/JSON: hex ids, integer enums, 2-space indent).
3. `scripts/verify-ns-capture.sh [capture dir]` runs the check.
4. Each OTLP export's `.json` committed beside it; `CAPTURE.md` says they were
   added in the sandbox, decoded from the `.pb` (the captured files unchanged).
5. `docs/implicit-behaviours.md`: a notification-service section, N1:
   `/health/ready` hangs while Postgres is paused; not contract (the Rust port
   answers 503 within 2 s).

## Acceptance Criteria
- `scripts/ci.sh` green (unit tests for both modules, >80% coverage).
- `scripts/verify-ns-capture.sh` PASS on the capture; FAIL naming the file on
  an `http/*.txt` that is no exchange, an `otlp/*.json` whose spans differ
  from its `.pb`, a `sent_email` row with another status.
- gluon `bin/verify-complete-RPN-1.sh` PASS.

## Out of Scope
Checks against a running service (RPN-10 on); `stdout.log`, metrics and
`requests.jsonl` contents beyond "each `.jsonl` line is JSON".

## Decided during the track (2026-11-11, with the user)
- **Errors:** only what the checks above define is a problem (`FAIL` naming the file).
  Anything else (a missing file, bytes that aren't UTF-8, a `.pb` that `decode-otlp`
  can't read) raises the parser's own exception, as reading user-service's capture
  does (`capture_file`, `load_exchange`). Handling for inputs no real capture has
  shown was written, then removed: a test comes from a problem seen in a real
  capture, and only then is its handling decided.
- **The table carries each record's exact `value` and `traceparent`** (beyond FR1),
  so the consumer checks (RPN-10 on) can publish the same records; a test shows
  the values equal the captured dead letters byte for byte.
