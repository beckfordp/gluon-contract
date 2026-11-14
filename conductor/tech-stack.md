# Tech Stack — gluon-contract

Status (2026-11-08): set at conductor setup, for RUST-1.1. Items marked
**Open** are decided, and recorded here with a dated note, in the PLAN item
that first needs them, before any code depends on them.

## Language / runtime
- **Python 3.13** (`.python-version`), fully type-annotated
- **uv 0.9** — installs the pinned Python, manages the venv, and locks every
  dependency in `uv.lock` (committed). Chosen over gluon's existing
  `python3 -m venv` + `requirements.txt` pattern (`bin/obs-dashboards`)
  because this repo has a dev toolchain and transitive dependencies worth
  locking, and one tool covers the Python version too. `uv sync --locked` in
  CI fails if the lock is stale.
- Build backend `uv_build`; `src/` layout, package `gluon_contract`

## Test stack
- **pytest 9.2** — runner for the harness's own tests (`tests/`) and the
  contract checks (`checks/`). `testpaths = ["tests"]`, so a bare `pytest`
  and CI never run contract checks. *(2026-11-09, RUST-1.2: deviation from
  RUST-1.1.)* `tests/integration/` starts local processes — throwaway
  Postgres, the OTLP stub, a stand-in target — so CI does too; still no
  Docker and no cluster. *(2026-11-10, portable-harness)* Runs on macOS and
  Ubuntu; on macOS Homebrew `postgresql@16`
  (`CONTRACT_PG_BIN=$(brew --prefix postgresql@16)/bin`). The CI run is local
  (`scripts/ci.sh`, as in the sandbox); GitHub Actions is
  parked (backlog). A full ci.sh run takes about 95 s.
- pytest's own **pytester** (`-p pytester` in `addopts`) proves the `checks/`
  wiring with throwaway suites
- **pytest-cov 7.1** — coverage on `src/gluon_contract`, gate 80%

## Lint / format / types
- **ruff 0.17** — formatter and linter (pyflakes, pycodestyle, isort, bugbear,
  pyupgrade, simplify, pytest style, naming, ruff's own rules)
- **mypy 2.4**, `strict = true`, over `src/` and `tests/`; **types-protobuf
  7.35.1.20260906** *(2026-11-09)*, because protobuf ships no type information

Tool versions are pinned exactly in `pyproject.toml`; bump them deliberately.

## Sandbox
Developed and run in the sandbox (ADR 0028). gluon `plans/private/sandbox.md` (laptop only) records
it; `bin/sandbox-setup` rebuilds it (including this repo's `.venv`). A tool
added here that the sandbox doesn't already have is added to
`bin/sandbox-setup` in the same change.

## Layout
- `src/gluon_contract/` — the harness's own code (typed: `py.typed`):
  `config`, `env_contract`, `ports`, `postgres`, `otlp` + `otlp_stub`,
  `target`, `harness`, `contracts`, `pytest_plugin`; *(2026-11-11, RPN-1)*
  `notification_scenarios` (what notification-service's capture drove) and
  `notification_capture` (that capture checked on its own; `python -m` entry point);
  *(2026-11-12, RPN-3)* `services` (each service's profile: the broker,
  topics and called services the harness starts for it) and
  `check_markers` (each check module's service, read with `ast`; CI requires
  one on every module in `checks/`); *(2026-11-13, RPN-4)* `sent_email`
  (notification-service's captured rows as seed data) and `expect` (response
  comparisons for any service's checks, failures spelled out since pytest
  doesn't rewrite asserts in `src/`)
- `tests/unit/` (pure) and `tests/integration/` (local processes, including
  `stand_in_target.py`, a test double for the build under test) — run in CI
- `checks/` — the contract checks, one module per group (RUST-1.3 onwards),
  each marked with the service it judges (`pytest.mark.service`, RPN-3);
  `checks/conftest.py` imports the wiring from `gluon_contract.pytest_plugin`
  (pytest allows `pytest_plugins` only in the root conftest). Run by path;
  type-checked by a separate `mypy checks` (its `conftest` module name would
  clash with `tests/integration/`'s)
- `contracts/` — Scala-generated artifacts (OpenAPI, Swagger UI, AsyncAPI
  JSON and HTML) and captures of Scala behaviour, produced on the laptop on
  request, each with a `PROVENANCE.md`

## Planned libraries (**Open** until the item that needs them)
- *(2026-11-08, built in RUST-1.2)* No Docker in the sandbox: isolated mode
  runs everything as local processes — a throwaway PostgreSQL 16 cluster via
  `initdb`/`pg_ctl`, the build under test in its own process group — with the
  standard library only (`subprocess`, `urllib`, `http.server`)
- *(2026-11-09, decided for RUST-1.3/1.5)* Postgres: **psycopg 3.3.7**
  (`psycopg[binary]`, pinned) for checks that read the service's database
- HTTP in checks: the standard library's `http.client`, not httpx: checks
  need exact control over methods, headers (including none) and raw bodies,
  and see exactly what the service sent back
- OpenAPI response validation and spec comparison — RUST-1.4
- *(2026-11-09, decided for RUST-1.6/1.7, all pinned)* **jsonschema 4.26.0**
  (payloads against `registry/` draft-07 schemas), **pyyaml 6.0.3** (the
  Debezium connector config in gluon `infra/`), **prometheus-client 0.26.0**
  (its text-format parser for `/metrics`); dev: types-jsonschema, types-pyyaml
- *(2026-11-09, decided for RUST-1.2 Phase 3)* OTLP/HTTP receiver stub:
  **opentelemetry-proto 1.45.2** (with its protobuf) for the
  `ExportTraceServiceRequest` messages, on the standard library's
  `ThreadingHTTPServer`. Accepts `application/x-protobuf` (what the Java and
  Rust exporters send by default) and `application/json` (OTLP/JSON: hex ids,
  integer enums), optionally gzip-encoded. Pinned exactly, like the dev tools.
- Kafka client for the CDC stack, the probe group and cluster mode — RUST-1.8/6.1
- The CDC stack's jars (Kafka, Kafka Connect, Debezium) from Maven Central,
  run on the sandbox's Java 21 — RUST-1.8

## CI
- `scripts/ci.sh` defines the checks once: `uv sync --locked`, `ruff format
  --check`, `ruff check`, `mypy` (then `mypy checks`), `pytest` with the
  coverage gate over unit and integration tests. Local processes, no Docker,
  no cluster, no contract checks.
- The sandbox runs `scripts/ci.sh` directly. GitHub Actions on `ubuntu-latest`
  (`astral-sh/setup-uv`, uv pinned) runs the same script once the repo is
  pushed *(2026-11-08: deferred, no GitHub access from the sandbox)*.
