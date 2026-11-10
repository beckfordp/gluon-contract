# Spec — RUST-1.2: Isolated-mode runner

## Overview
The harness can stand up a throwaway world for the build under test and tear it
down again (gluon PLAN.md RUST-1.2, ADR 0028 decision 3): a PostgreSQL 16
cluster from the local binaries, an OTLP/HTTP stub that captures spans, and the
build under test started as a local process with the service's env-var
contract, its stdout captured and its `/metrics` scrapeable. No contract checks
yet (RUST-1.3 onwards). There is no implementation of user-service in the
sandbox yet, so the runner is proven against a **stand-in target**: a test
double that honours the env-var contract. It is not a model of user-service.

## Functional Requirements
1. **Config (pure):** `HarnessConfig` from pytest options or `CONTRACT_*` env
   vars — target command (required; shell-style split), target working
   directory, target name (a label for reports), service name (default
   `user-service`), Postgres binary directory (`CONTRACT_PG_BIN`, else the
   directory of `pg_ctl` on the `PATH`, symlinks resolved), readiness path
   (default `/health/ready`), readiness deadline (default 60 s), keep-artifacts
   flag. Invalid config raises one `ConfigError` listing every problem.
2. **Env-var contract (pure):** the variables the service reads, and nothing
   else from the harness's own environment. Source: user-service
   `application.conf` and gluon `environments/local/user-service.values.yaml`.
   For service `<domain>-service`: `<DOMAIN>_SERVICE_PORT`,
   `<DOMAIN>_SERVICE_METRICS_PORT`, `POSTGRES_HOST`, `POSTGRES_PORT`,
   `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` (database, user and
   password are the domain name, as in gluon-local), and
   `OTEL_EXPORTER_OTLP_ENDPOINT`. A minimal base is passed through so the
   process can run: `PATH`, `HOME`, `LANG`, `TZ`, `JAVA_HOME` when set.
3. **Throwaway Postgres:** `initdb` into a temporary directory; the domain user
   as superuser with a scram-sha-256 password over TCP (trust only on the
   cluster's private Unix socket); the domain database created;
   `wal_level=logical` (for RUST-1.8); listening on `127.0.0.1` on a free port.
   `stop()` and `start()` for later checks (readiness 503), removal on exit.
   Failures carry the tail of the server log.
4. **OTLP/HTTP stub:** listens on `127.0.0.1` on a free port; `POST /v1/traces`
   with `application/x-protobuf` or `application/json` answers 200 with an
   empty `ExportTraceServiceResponse`; anything else 404. Requests decode to
   typed spans (trace id, span id, parent span id, name, kind, the resource's
   `service.name`, attributes). `spans()` returns what arrived;
   `wait_for_spans(predicate, deadline)` polls.
5. **Target process:** started with the configured argv, working directory and
   the env-var contract, in its own process group; stdout and stderr go to a
   log file whose lines the harness can read. Ready when `GET <readiness path>`
   answers 200 before the deadline; if the process exits or the deadline
   passes, `TargetError` with the exit code and the log tail. Stopped with
   SIGTERM to the group, SIGKILL after 10 s.
6. **Metrics:** `scrape_metrics()` returns the body of
   `GET http://127.0.0.1:<metrics port>/metrics`.
7. **Harness:** a context manager that starts Postgres, then the OTLP stub,
   then the target, and tears down in reverse even when a step fails. Its work
   directory is removed unless keep-artifacts is set. Exposes the base URL,
   metrics URL, Postgres connection details, the OTLP stub and the log lines.
8. **Wiring for `checks/`:** `checks/conftest.py` with `--target-cmd`,
   `--target-cwd`, `--target-name`, `--keep-artifacts` and a session-scoped
   `harness` fixture. No checks yet.
9. **`contracts/` provenance:** a unit test that every capture directory under
   `contracts/<service>/` holds a `PROVENANCE.md`.
10. **Test layout:** `tests/unit` (pure) and `tests/integration` (starts local
    processes: Postgres, the stub, the stand-in target). Both run under a bare
    `uv run pytest` and `scripts/ci.sh`; `checks/` never does. The stand-in
    target (`tests/integration/stand_in_target.py`) serves `/health`,
    `/health/ready` (200 when Postgres accepts a TCP connection), `/__env` (the
    contract variables it received), `/metrics`, prints one JSON log line, and
    exports one span to the OTLP endpoint.

## Non-Functional Requirements
- No fixed sleeps: every wait polls with a deadline
- Nothing survives a run, including a failed one: no processes, no
  directories (unless keep-artifacts)
- Only the PostgreSQL binaries and Python; no Docker
- `scripts/ci.sh` green; coverage ≥ 80% across unit and integration tests
- **Deviation from RUST-1.1 (recorded in `tech-stack.md`):** CI now starts
  local processes (Postgres, the stub, the stand-in target). Still no Docker,
  no cluster and no contract checks. GitHub's ubuntu runners ship
  PostgreSQL 16, found via `CONTRACT_PG_BIN`.

## Acceptance Criteria
- `scripts/ci.sh` green in the sandbox
- The integration tests show: the stand-in target receives exactly the
  env-var contract; its log line and span are captured; `/metrics` scrapes;
  the target connects to Postgres over TCP with the password; a target that
  exits early, or never gets ready, fails with its log tail; after every test
  no process or work directory is left
- `uv run pytest checks --target-cmd "…"` starts and stops the world (no checks
  collected yet)

## Out of Scope
- Any contract check (RUST-1.3 onwards)
- Kafka, Kafka Connect, Debezium (RUST-1.8); the probe's HTTP stub (RUST-6.1)
- Cluster mode (RUST-5.4)
