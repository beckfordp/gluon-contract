# Spec — RUST-6.1: Probe stubs

## Overview
gluon PLAN.md RUST-6.1 (ADR 0028 decision 8): what the probe group needs
around the consumer probe — a throwaway Kafka broker (the CDC stack's, from
the same Maven Central jars) that a check can produce to, read from, stop and
start again, and a scriptable HTTP stub standing in for user-service's
`GET /users/{id}` (ADR 0025's recipient lookup) that can answer 5xx, delay or
reset the connection.

## Functional Requirements
1. `KafkaBroker` (in `cdc.py`, shared with `CdcStack`): KRaft, gluon-local's
   cluster id; `produce(topic, key, value, headers)`; `record(topic, until)`
   (from the beginning); `stop()` then `start()` on the same port and data (an
   outage), `committed(group, topic)` offsets.
2. `HttpStub` (`http_stub.py`): answers `GET /users/{id}` with user-service's
   200 body by default; `script(*behaviours)` queues the next answers —
   `Status(code)`, `Delay(seconds, then)`, `Reset()` (closes the connection
   without answering); records every request (method, path, headers).
3. Fixtures `kafka` and `lookup_stub` for the probe group.

## Acceptance Criteria
- CI green (unit tests for the stub, integration test for the broker's outage
  and produce/read); `scripts/verify-probe-stubs.sh` PASS.
