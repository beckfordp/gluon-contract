# Spec — RUST-5.4 (prepared): cluster mode

## Overview
gluon PLAN.md RUST-5.4 runs the harness in cluster mode on the laptop: against
whichever implementation gluon-local has deployed, the REST and docs groups
and the real `user-events` record. ADR 0028's criterion: "Cluster mode is
green for whichever implementation is deployed". The mode itself is harness
code, so it is built and tested here, against a locally started Rust service
standing in for the deployment, with the sandbox CDC stack as its Kafka.

## Functional Requirements
1. `CONTRACT_BASE_URL` (or `--base-url`) switches to cluster mode: nothing is
   started; `harness.base_url` is that URL; only checks marked `cluster` run,
   every other one is skipped saying it needs isolated mode.
2. The REST checks that need nothing but the API, the docs group, and a new
   topic check are marked `cluster`.
3. The topic check reads `user-events` through a console consumer command:
   isolated mode, the CDC stack's broker; cluster mode,
   `CONTRACT_KAFKA_CONSOLE_CONSUMER` (default: `kafka-console-consumer.sh` in
   gluon-local's Kafka pod via `kubectl exec`). A signup's record: key the
   userId, the envelope, `traceparent` in the request's trace, sampled,
   `correlation_id`, and the router's `id`.

## Acceptance Criteria
- CI green, including an integration test running the cluster checks against a
  started service and the CDC stack; `scripts/verify-cluster-mode.sh` PASS.
