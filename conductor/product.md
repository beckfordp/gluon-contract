# Initial Concept

Black-box contract harness — per gluon ADR 0028 and gluon `plans/rust-port/user-service/plan.md`: a
Python + pytest program that exercises every wire contract of a Gluon service
and checks it for correctness, against any implementation of it. First target:
user-service. The reference is the specified contracts; the Rust port
(`user-service-rs`) is the implementation under judgement, and the Scala
service confirms the expectations on the laptop.

# Product — gluon-contract

## Purpose
Turn a service's wire contracts, written down and implicit, into executable
checks that run against any implementation of that service (ADR 0028
decision 3). The contracts: REST, docs, Postgres schema and stored formats,
outbox rows and the Kafka envelope, traces, metrics, logs and runtime config.

## Where expectations come from (ADR 0028 decision 2)
In order of precedence:
1. the documented contracts: gluon `docs/system-design.md`, `registry/`, the
   ADRs;
2. the contract artifacts the Scala build generates (OpenAPI spec and Swagger
   UI, AsyncAPI JSON and HTML), produced on the laptop on request and kept in
   `contracts/` with their provenance;
3. the Scala repo's executable specifications (its test suites and
   `verify-*.sh` scripts), read as specifications;
4. behaviour none of these pins down, captured from the Scala service on the
   laptop on request, also kept in `contracts/`.

## Users
- The consultant (solo): runs it in the sandbox against the Rust service, and
  once on the laptop against the Scala service to confirm the expectations
- Reviewers of the user-service port: read the check names and failure messages as
  the list of contracts

## Goals
- **Isolated mode** (default; the sandbox's only mode): starts the build under
  test as a local process, with its external dependencies stubbed over the
  wire — an OTLP/HTTP receiver for spans, the harness itself scraping
  `/metrics` and reading stdout for logs, the registered Debezium routing
  applied to `outbox_events` in place of Debezium, and a throwaway
  PostgreSQL 16 cluster from the local binaries (the schema is itself a
  contract)
- **Sandbox CDC stack** (RUST-1.8): Kafka, Kafka Connect and the Debezium
  Postgres connector from Maven Central jars, to check the real
  `user-events` record
- **Cluster mode** (laptop only, RUST-5.4): the REST checks against
  gluon-local, plus the real `user-events` topic
- Every failure names the contract, its source, and expected vs actual
- The consumer probe's checks (RUST-6), against the CDC stack's Kafka
  broker and a scriptable HTTP stub

## Non-goals
- Testing through gshop or user journeys (gluon-acceptance does that)
- Load or latency (gluon-performance; the Rust comparison is a later follow-up)
- Deriving an expectation from the Rust code
- Running contract checks or a cluster in CI: CI is format, lint, type check
  and the harness's own unit and integration tests (`scripts/ci.sh`), which
  start local processes only

## Scope (from gluon PLAN.md; items owned by this repo)
RUST-1 (RUST-1.1–1.9), RUST-5's Scala confirmation and
cluster-mode run (RUST-5.0, 5.4), and RUST-6's stubs and probe group
(RUST-6.1, 6.5). Worked one PLAN item at a time, outside-in: each check group
is written, and seen failing for the stated reason, just before the Rust items
that turn it green. Each track ends with a review.

## Constraints
Developed and run in the sandbox (ADR 0028): local processes only, no Docker,
no cluster, no GitHub, no Scala build; only Rust, Python and (if needed)
TypeScript change there. Scala-generated artifacts and captures come from the
laptop on request. Laptop budget per ADR 0015. No production data anywhere, so
cluster mode may create throwaway accounts, which `bin/reset-data` clears.
