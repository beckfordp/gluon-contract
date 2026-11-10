# gluon-contract

Black-box wire-contract harness for the [Gluon](https://github.com/beckfordp/gluon)
platform. It exercises every wire contract of a service — REST, docs, Postgres
schema and stored formats, outbox rows and the Kafka envelope, traces, metrics,
logs, runtime config — and checks each one for correctness, against any
implementation of that service.

First target: user-service. The reference is the specified contracts: the
documented contracts, the Scala-generated OpenAPI/AsyncAPI artifacts, the
Scala repo's test suites and `verify-*.sh` scripts, and behaviour captured
from the Scala service on request. The Rust port (`user-service-rs`) is judged
against them; the Scala service confirms them on the laptop. See
[ADR 0028](https://github.com/beckfordp/gluon/blob/main/docs/adr/0028-rust-port-spike-user-service.md)
for why, and gluon's `PLAN.md` "Rust Spike" for the order of work.

**Status:** the isolated-mode runner is built (RUST-1.2); the check groups
arrive one PLAN item at a time (RUST-1.3 onwards); see
[`conductor/tracks.md`](./conductor/tracks.md).

## Prerequisites

- [uv](https://docs.astral.sh/uv/) 0.9 — installs the pinned Python (3.13) and
  the locked dependencies
- PostgreSQL 16 binaries (`initdb`, `pg_ctl`, `createdb`): found through
  `pg_ctl` on the `PATH`, or set `CONTRACT_PG_BIN`. Isolated mode runs
  everything as local processes (no Docker). The tests use them too.
- To run checks: a build of the implementation under test
- Cluster mode (RUST-5.4, laptop only): the gluon-local cluster

No GitHub Packages token is needed.

## Commands

```
uv sync                                   # Python + locked dependencies
uv run pytest                             # the harness's own unit + integration tests
scripts/ci.sh                             # what CI runs: format, lint, types, tests
scripts/verify-isolated-runner.sh         # RUST-1.2, verified end to end (~100 s; --skip-ci)
```

Each track has a `scripts/verify-<track>.sh` that checks what the track set
out to do, reporting each result as it finds it.

## Running the contract checks

```
uv run pytest checks --target-cmd "<command that starts the build under test>"
```

The first check that asks for the `harness` fixture starts, in a fresh work
directory: a throwaway PostgreSQL 16 cluster (the service's domain user and
database, password over TCP, `wal_level=logical`), an OTLP/HTTP stub for its
spans, then the build under test with the env-var contract (its ports,
`POSTGRES_*`, `OTEL_EXPORTER_OTLP_ENDPOINT`, and only `PATH`, `HOME`, `LANG`,
`TZ`, `JAVA_HOME` from your environment). Everything stops at the end of the
session, even after a failure.

| Option | Variable | Default |
|---|---|---|
| `--target-cmd` | `CONTRACT_TARGET_CMD` | required |
| `--target-cwd` | `CONTRACT_TARGET_CWD` | the current directory |
| `--target-name` | `CONTRACT_TARGET_NAME` | the command's first word |
| — | `CONTRACT_SERVICE` | `user-service` |
| — | `CONTRACT_PG_BIN` | the directory of `pg_ctl` on the `PATH` |
| — | `CONTRACT_READINESS_PATH` | `/health/ready` |
| — | `CONTRACT_READINESS_DEADLINE` | `60` (seconds) |
| `--keep-artifacts` | `CONTRACT_KEEP_ARTIFACTS` | off: keep the work directory (target and Postgres logs, data) |

## Layout

- `src/gluon_contract/` — the harness: config, env-var contract, throwaway
  Postgres, OTLP decoding and stub, target process, harness, `contracts/`
  rules, pytest wiring
- `tests/unit/`, `tests/integration/` — the harness's own tests (CI runs
  both; the integration tests start local processes, including a stand-in
  target)
- `checks/` — the contract checks, one module per contract group (RUST-1.3
  onwards); always run by path
- `contracts/` — Scala-generated artifacts and captures from the laptop, each
  with a `PROVENANCE.md`
- `conductor/` — product, tech stack, workflow and tracks
