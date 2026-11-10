# Spec — RUST-5.2 (rehearsal): the implementation switch's Debezium sequence

## Overview
gluon PLAN.md RUST-5.2 runs on the laptop, but its riskiest step can be
rehearsed on the sandbox CDC stack: switching implementation resets the `user`
database's `public` schema (ADR 0028 decision 5), so Debezium's publication
loses `outbox_events`; the new service recreates the table, and the connector
must then publish its rows. The sequence `bin/k8s-local-up` will run: drop
and recreate the schema, drop `dbz_publication`, deploy (the service
migrates), restart the connector with its tasks.

## Functional Requirements
1. `CdcStack.restart_connector()`: Connect's REST
   `POST /connectors/<name>/restart?includeTasks=true`, then waits until the
   connector streams again.
2. An integration test: after the sequence, a new row reaches `user-events`.

## Acceptance Criteria
- CI green with the test passing.
