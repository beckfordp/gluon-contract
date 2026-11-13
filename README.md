# gluon-contract

Black-box wire-contract harness for the [Gluon](https://github.com/beckfordp/gluon)
platform. It exercises every wire contract of a service — REST, docs, Postgres
schema and stored formats, outbox rows and the Kafka envelope, traces, metrics,
logs, runtime config — and checks each one for correctness, against any
implementation of that service.

First target: user-service; the second, notification-service (gluon ADR 0029),
arrives one check group at a time. A run judges one service (`--service`).
The reference is the specified contracts: the documented contracts, the
Scala-generated OpenAPI/AsyncAPI artifacts, the Scala repo's test suites and
`verify-*.sh` scripts, and behaviour captured from the Scala service on
request. The Rust port (`user-service-rs`) is judged
against them; the Scala service confirms them on the laptop. See
[ADR 0028](https://github.com/beckfordp/gluon/blob/main/docs/adr/0028-rust-port-spike-user-service.md)
for why, and gluon's `plans/rust-port/user-service/plan.md` for the order of work.

**Status:** the isolated-mode runner is built (RUST-1.2); user-service's
check groups are done (RUST-1.3 to RUST-6.x); the harness starts
notification-service too (RPN-3), whose groups arrive one session at a time:
its REST group (`checks/test_notification_rest.py`, RPN-4) is written and red
against the walking skeleton until the Rust session that implements it; see
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
scripts/verify-notification-capture.sh [dir]        # RPN-1: a notification-service capture checked on its own
scripts/verify-multi-service-harness.sh   # RPN-3: the service as a parameter (~15 min; --skip-ci, --skip-contract)
scripts/verify-notification-rest-group.sh # RPN-4: notification-service's REST group, red on the skeleton (~8 min; --skip-ci)
scripts/verify-check-group.sh checks/test_<group>.py [--service NAME] [--expect-green | --expect-red PATTERN]
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

### More than one service

A run judges one service: `--service` (`CONTRACT_SERVICE`), default
`user-service`. What each service needs beyond Postgres and the OTLP stub is
its profile in `src/gluon_contract/services.py`, from its `application.conf`
and gluon `environments/local/<service>.values.yaml`:

| Service | Also started | Also in its env contract |
|---|---|---|
| `user-service` | — | — |
| `notification-service` | a Kafka broker (the CDC stack's jars) with `user-events`, `order-events`, `payment-events`, `fulfilment-events` created; a scriptable stub each for user-service and order-service | `KAFKA_BOOTSTRAP_SERVERS`, `USER_SERVICE_URL`, `ORDER_SERVICE_URL` |

The broker's jars are checked before anything starts (`CONTRACT_CDC_HOME`, default
where gluon `bin/sandbox-setup --only cdc` puts them). Checks reach them as
`harness.kafka` and `harness.stubs["<service>"]`.

A check module marked `pytest.mark.service("<name>")` is that service's
contract: a run for another service deselects it. The plugin runs unmarked
checks for any service, but CI requires every module in `checks/` to carry a
marker naming known services (`tests/unit/test_check_markers.py`); a check that
really is service-neutral names them all. notification-service's groups
arrive one session at a time, the first its REST group (RPN-4):

```
uv run pytest checks --service notification-service --target-cmd "<its build>"
```

runs `checks/test_notification_rest.py` and deselects every user-service
group. Until its consumers exist (RPN-10 on), nothing creates `sent_email`
rows through the API, so its `/emails` checks seed the table with the
capture's own rows (`gluon_contract.sent_email`) and expect the capture's
answers; comparisons any service's checks can use are in
`gluon_contract.expect`.

| Option | Variable | Default |
|---|---|---|
| `--service` | `CONTRACT_SERVICE` | `user-service` (or `notification-service`) |
| `--target-cmd` | `CONTRACT_TARGET_CMD` | required |
| `--target-cwd` | `CONTRACT_TARGET_CWD` | the current directory |
| `--target-name` | `CONTRACT_TARGET_NAME` | the command's first word |
| — | `CONTRACT_PG_BIN` | the directory of `pg_ctl` on the `PATH` |
| — | `CONTRACT_READINESS_PATH` | `/health/ready` |
| — | `CONTRACT_READINESS_DEADLINE` | `60` (seconds) |
| `--keep-artifacts` | `CONTRACT_KEEP_ARTIFACTS` | off: keep the work directory (target and Postgres logs, data) |

## Layout

- `src/gluon_contract/` — the harness: config, service profiles, env-var
  contract, throwaway Postgres, OTLP decoding and stub, target process, harness, `contracts/`
  rules, pytest wiring; notification-service's capture check and scenario
  table (`notification_capture`, `notification_scenarios`; RPN-1); its captured `sent_email` rows as
  seed data (`sent_email`) and response comparisons for any service (`expect`; RPN-4)
- `tests/unit/`, `tests/integration/` — the harness's own tests (CI runs
  both; the integration tests start local processes, including a stand-in
  target)
- `checks/` — the contract checks, one module per contract group (RUST-1.3
  onwards); always run by path
- `contracts/` — Scala-generated artifacts and captures from the laptop, each
  with a `PROVENANCE.md`
- `conductor/` — product, tech stack, workflow and tracks
