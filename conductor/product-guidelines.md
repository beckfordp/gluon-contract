# Product Guidelines — gluon-contract

## Code conventions
Canonical: [`code_styleguides/python.md`](./code_styleguides/python.md)
(+ `general.md`). Fully typed, `mypy --strict` clean, ruff clean.

## Black-box only
- Checks talk to the implementation only over its wire contracts: HTTP, the
  database it owns, its metrics port, its stdout, the spans it exports.
- An expectation comes from the reference, in `product.md`'s order: documented
  contracts, Scala-generated artifacts in `contracts/`, the Scala repo's test
  suites and `verify-*.sh` scripts, or a capture in `contracts/`. Each check's
  docstring names its source. Never derive an expectation from the Rust code,
  and don't read Scala production code to decide one: if nothing above pins a
  behaviour down, ask for a capture.
- Behaviour the Scala service shows but nothing documents is still a contract
  (ADR 0028 decision 2). It is recorded as a check and listed for RUST-1.9.

## Checks
- Grouped by contract, one module per group under `checks/`: REST, docs,
  schema and stored formats, outbox and envelope, traces, metrics, logs,
  config, consumer probe
- One behaviour per check; the name says the contract ("login with an unknown
  email answers the same 401 body as a wrong password")
- Failure messages give the contract, its source, expected and actual
- Everything in `contracts/` is committed with a `PROVENANCE.md` (who ran
  what, where, and the user-service commit) and only replaced deliberately,
  by a new capture

## Test data and async
- Every run creates unique throwaway data (emails `contract-<uuid>@example.com`,
  obviously fake passwords); never demo accounts
- Isolated mode starts and stops its own processes and removes their data
  directories; nothing survives a run
- Async outcomes (spans arriving, outbox rows) are polled with deadlines; no
  fixed sleeps
- Cluster mode only adds throwaway accounts; `bin/reset-data` clears them

## Testing / quality gate
- Before every commit: `scripts/ci.sh` (format, lint, types, unit tests; CI
  runs the same script)
- The harness's own helpers are unit-tested (>80% coverage); the checks are
  themselves the integration tests, run in the sandbox (isolated mode) or
  against gluon-local (cluster mode)
