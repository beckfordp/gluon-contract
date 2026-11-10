# Spec — RUST-1.8: Sandbox CDC stack

## Overview
gluon PLAN.md RUST-1.8 (ADR 0028 "Outbox and envelope" row: "the routed
record"). The outbox group applies the connector's routing to the row
(`routing.py`); this runs the real thing in the sandbox: the harness's Postgres
(already `wal_level=logical`), a KRaft Kafka broker and a standalone Kafka
Connect worker with Debezium's Postgres connector, from the Maven Central jars
gluon `bin/sandbox-setup --only cdc` installs (Kafka 3.8.0, Debezium
3.0.0.Final, as gluon-local), registered with gluon's connector config. Cluster
mode against gluon-local stays RUST-5.4.

## Functional Requirements
1. `gluon_contract/cdc.py`: `CdcStack` (broker: formatted with gluon-local's
   cluster id, then started; worker: StringConverter key and value as
   gluon-local's, the connector from `debezium-connectors-register.yaml` with
   only the database address and login replaced), ready once Debezium streams;
   stops everything it started; a clear error when the jars are missing.
   `records(topic, until, timeout)` reads a topic from the beginning (kafka-python).
2. The `cdc` fixture (session), on demand: only the CDC group uses it.
3. `checks/test_cdc.py`: a signup's record on `user-events` — key the userId,
   value the row's `payload` text, headers `traceparent` (the row's
   `trace_parent`), `correlation_id` and the router's `id` (the row id); and
   `routing.route` gives exactly the real record (the outbox group's stand-in
   is faithful), which needs `id` added to the stand-in.

## Acceptance Criteria
- `scripts/verify-cdc-group.sh` PASS: CI green; jars present; the group green
  against the Rust build.
