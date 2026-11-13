# Capturing notification-service's contract artifacts (laptop)

The sandbox can't build the Scala service (ADR 0028, "two environments"), so
the artifacts its build generates, and the behaviour nothing documents, are
produced on the laptop by gluon's `contract-notification.sh` and committed
here as `contracts/notification-service/<date>/`. Each capture carries the
script that made it as `CAPTURE.sh`, and its own `PROVENANCE.md` (commit, date,
JDK, images).

Run it from gluon's root with Docker running and `GITHUB_TOKEN` set (purerest
from GitHub Packages; it falls back to `gh auth token`). It uses its own
containers and ports, none of which clash with gluon-local: Kafka 19092,
Postgres 15432, the service 18080 (metrics 19091), the stub 18090. Output:
`~/notification-service-contracts-<date>/` and a `.tgz` beside it.

## What it does

1. Builds and stages the Scala service; copies the AsyncAPI JSON and HTML.
2. Starts Kafka and Postgres containers, creates the four input topics, and
   starts `stub.py`: user-service, order-service and an OTLP receiver in one,
   logging every request to `requests.jsonl` and keeping trace exports raw in
   `otlp/`. `stub.py` passes this repo's ruff, which the script checks.
3. Runs the service against them; `stdout.log` holds its JSON logs.
4. Drives every consumer path on `user-events`, `order-events`,
   `payment-events` and `fulfilment-events`: each email, duplicates,
   unrelated types, undecodable envelopes and payloads, each cancel reason,
   guest fallback, unresolved recipients, an unknown order; then waits until
   `sent_email` and the stub's log stop changing.
5. Records the REST surface in `http/`: docs, health, `/emails` filters and
   edge cases, CORS, trace propagation.
6. Last, a user lookup that always fails (it opens the breaker).
7. Dumps the DLQs, consumer groups and topics (`kafka/`), the schema and
   rows (`db/`), and metrics at startup, after the events and at the end.
8. Readiness with Postgres paused, back, stopped and restarted (`http/health-*-pg-*.txt`,
   with curl's exit code and elapsed time: paused, the probe hangs).
9. Stops the service gracefully (flushing spans) and redacts laptop paths
   and Docker addresses before packing.

## Captures

- `20261111`: notification-service `b60d4d7`, clean tree. Committed as
  captured, no edits. Added in the sandbox (RPN-1), nothing else changed:
  `otlp/*.json`, each `otlp/*.pb` decoded to readable OTLP/JSON by
  `python -m gluon_contract.notification_capture decode-otlp`; its `check` command
  confirms each gives the same spans as its `.pb`.
