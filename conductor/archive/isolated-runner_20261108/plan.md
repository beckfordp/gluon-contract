# Plan — RUST-1.2: Isolated-mode runner

## Phase 1: Config and env-var contract (pure) [checkpoint: 5eae841]

*Deviation (2026-11-08): `service_env` takes a typed `Endpoints` value (mypy --strict rejected a plain dict of mixed types).*

- [x] Task: move `tests/test_package.py` to `tests/unit/`; write failing tests for `HarnessConfig` — defaults, `CONTRACT_*` overrides, every invalid value reported in one `ConfigError`, Postgres binary directory explicit / from `pg_ctl` on the `PATH` (symlink resolved) / missing a5c6ba3
- [x] Task: implement `gluon_contract/config.py` 6915047
- [x] Task: write failing tests for `service_env` — variable names derived from the service name, the exact set, database/user/password from the domain, the minimal base passed through, nothing else leaked 567cbd3
- [x] Task: implement `gluon_contract/env_contract.py` 456393b
- [x] Task: Conductor - User Manual Verification 'Phase 1: Config and env-var contract' (Protocol in workflow.md)

## Phase 2: Throwaway Postgres [checkpoint: 92646f6]

*Addition (2026-11-09): `config.find_pg_bin` (public form of the lookup `load_config` does), for the integration tests' `pg_bin` fixture; its own unit test came first.*

- [x] Task: write failing integration tests — cluster starts on a free port, TCP + password login as the domain user, domain database exists, `wal_level` is `logical`, `stop()`/`start()`, directory removed on exit, a failed start carries the server log tail a898ffe
- [x] Task: implement `gluon_contract/postgres.py` (and the free-port helper) 9c56c82
- [x] Task: Conductor - User Manual Verification 'Phase 2: Throwaway Postgres' (Protocol in workflow.md)

## Phase 3: OTLP/HTTP stub [checkpoint: beb89f0]

*Additions to spec FR4 (2026-11-09): a malformed body answers 400 and an unknown media type 415 (not 404), with the reason kept in `rejected()`; gzip and deflate bodies accepted; an attribute sent without a value decodes to None; `types-protobuf` added (protobuf ships no type information); a missed deadline raises `OtlpStubTimeoutError`, an AssertionError, because it is a contract failure.*

- [x] Task: add `opentelemetry-proto` (tech-stack first); write failing unit tests decoding protobuf and JSON `ExportTraceServiceRequest`s to typed spans fa524cf 46293ac
- [x] Task: implement the decoder f1e670c
- [x] Task: write failing integration tests — `POST /v1/traces` both encodings answers 200 with an empty response, other paths 404, `wait_for_spans` returns on arrival and fails at its deadline d4884b6
- [x] Task: implement `gluon_contract/otlp_stub.py` 7303315
- [x] Task: Conductor - User Manual Verification 'Phase 3: OTLP/HTTP stub' (Protocol in workflow.md)

## Phase 4: Target process and harness [checkpoint: d48b9ab]

*Additions (2026-11-09): `TargetProcess.wait_for_log` / `LogTimeoutError` (an AssertionError) — a target can be ready before it logs, found as a flaky first run, so log checks poll like span checks; `Harness(work_root=...)` so tests can see that nothing is left; the stand-in reports `/proc/self/environ`, because Python adds `LC_CTYPE` to its own environment when no locale is set (PEP 538). Three repeated integration runs green, nothing left behind.*

- [x] Task: write the stand-in target (test double) e6c4527
- [x] Task: write failing integration tests — env-var contract received exactly, log line captured, span captured by the stub, `/metrics` scraped, readiness; early exit and missed deadline fail with the log tail; stop kills the process group; the harness tears down in reverse on failure and leaves nothing behind e6c4527
- [x] Task: implement `gluon_contract/target.py` and `gluon_contract/harness.py` 7cbcbff
- [x] Task: Conductor - User Manual Verification 'Phase 4: Target process and harness' (Protocol in workflow.md)

## Phase 5: Wiring and docs [checkpoint: e691fad]

*Deviations (2026-11-09): the hooks and fixtures live in `gluon_contract/pytest_plugin.py`, imported by `checks/conftest.py` (pytest allows `pytest_plugins` only in the root conftest), which also makes the wiring testable with pytester; "`pytest checks --target-cmd …` starts and stops the world 9ad93cf e66e290" is proven with a pytester suite wired exactly like `checks/`, since `checks/` has no checks yet (run for real, it recognises the options, prints the target in the header and collects nothing); an unusable configuration ends the session as a usage error listing every problem; `py.typed` added and `checks/` type-checked by its own `mypy checks` run; `contracts.latest_capture` added for the checks to come. CI now ~80 s (integration tests start Postgres).*

- [x] Task: write failing unit test — every capture directory under `contracts/<service>/` has a `PROVENANCE.md`; implement 51daf56 cfd4bb0
- [x] Task: `checks/conftest.py` (options, session `harness` fixture); prove `uv run pytest checks --target-cmd …` starts and stops the world
- [x] Task: `tech-stack.md` (CI starts local processes; `opentelemetry-proto`), README 8f19fe2
- [x] Task: `scripts/verify-isolated-runner.sh` — verifies the whole track from outside (CI; config errors; a live run held open and probed with curl/psql/ps; teardown; a failed start; the `checks/` entry point; `contracts/`), reporting each result as found: 35 checks PASS; failure path shown with a deliberately wrong expectation 7fb7983
- [x] Task: Conductor - User Manual Verification 'Phase 5: Wiring and docs' (Protocol in workflow.md) — the user runs `scripts/verify-isolated-runner.sh`
