# Spec — RUST-1.7: Traces, metrics, logs and config groups

(gluon PLAN.md RUST-1.7; ADR 0028 "Traces", "Metrics", "Logs", "Config"
rows.) Reference: capture `stdout.log` (JSON log lines, spans as the Scala
service's console exporter printed them), `metrics.txt`, `db-outbox-events.jsonl`,
`http/traceparent-signup.txt`; purerest's ServerTracing contract (server span
per request, W3C continuation); ADR 0021/0027; application.conf.

- `checks/test_traces.py`: `service.name` user-service; a SERVER span
  `POST /auth/signup` with `http.request.method`, `url.path`,
  `http.response.status_code`, continuing an inbound `traceparent`; an
  INTERNAL `outbox.write` span in the same trace with `outbox.event_type` and
  `outbox.aggregate_id`; the row's `trace_parent` names that span, sampled.
- `checks/test_metrics.py`: after traffic, the service families of the
  capture (`http_server_request_duration_seconds`,
  `db_client_operation_duration_seconds`, `db_client_connection_*`,
  `users_registrations_total`, `users_logins_total`) with the same types,
  label names and histogram buckets; `http_route` raw with UUID segments as
  `{id}`; registrations counted by outcome, logins counted.
- `checks/test_logs.py`: JSON lines starting `{"@timestamp"` with the capture's
  base fields; request lines carry `method`, `path`, `trace_id`, `span_id`
  matching the request's span; no password or raw token ever logged.
- `checks/test_config.py`: invalid values stop startup (exit ≠ 0, nothing
  bound); `AUTH_PBKDF2_ITERATIONS`, `AUTH_ACCESS_TOKEN_TTL` and
  `USER_SERVICE_NAME` are honoured.

Helpers (unit-tested): metric shapes, traceparent parsing, capture files.
Acceptance: CI green; `scripts/verify-telemetry-groups.sh` PASS (red until
RUST-3.2–3.4).
