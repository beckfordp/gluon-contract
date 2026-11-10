# Spec — RUST-6.5: Probe group

## Overview
gluon PLAN.md RUST-6.5 (ADR 0028 decision 8, "Consumer probe" row), written
before the probe (RUST-6.2–6.4), as every group is. The probe is judged as
notification-service's consumers behave, from the reference: ADR 0025 (the
lookup and what to retry), `system-design.md` (unknown types skipped),
purekafka (`KafkaTracing.traced`, `DeadLetter`, `StreamSupervisor`,
`EventAge`, `ConsumerLag`, `Resilience` for the DLQ publish), purerest
(`Retry`, `CircuitBreaker`, `ClientTracing`, `ClientMetrics`), and
notification-service (`EnvelopeHandler`, `UserClient`, its config defaults).

## Functional Requirements
1. The probe's env contract (`probe.py`, documented in the events-probe
   README): `PROBE_KAFKA_BOOTSTRAP`, `PROBE_TOPIC`, `PROBE_GROUP_ID`,
   `PROBE_LOOKUP_URL`, `PROBE_METRICS_PORT`, `PROBE_SERVICE_NAME`, the
   resilience settings (`PROBE_LOOKUP_TIMEOUT`, `PROBE_LOOKUP_MAX_RETRIES`,
   `PROBE_LOOKUP_BASE_DELAY`, `PROBE_BREAKER_FAILURE_THRESHOLD`,
   `PROBE_BREAKER_RESET_TIMEOUT`, `PROBE_DLQ_MAX_RETRIES`,
   `PROBE_DLQ_BASE_DELAY`, `PROBE_RESTART_BASE_DELAY`,
   `PROBE_RESTART_MAX_DELAY`, `PROBE_LAG_INTERVAL`) and `OTEL_*`.
2. A `probe` fixture: starts the probe (`--probe-cmd`/`CONTRACT_PROBE_CMD`) on
   its own topic and group on the session's broker, with its own OTLP stub
   and the check's lookup stub; ready when its metrics answer.
3. `checks/test_probe.py`: lookup with the trace joined (consumer and client
   spans); unknown types skipped; poison dead-lettered with key and value;
   5xx and resets retried; a slow lookup timed out and retried; 404
   unresolved (one call, no DLQ); exhaustion dead-lettered after both retry
   layers; the breaker opening and rejecting; the purekafka and purerest
   metric names; the stream restarting after a broker outage.

## Acceptance Criteria
- `scripts/verify-probe-group.sh` PASS once RUST-6.2–6.4 are done; before,
  the group runs red for the stated reasons.
