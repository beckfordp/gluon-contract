# Spec — RUST-1.1: Contract harness scaffold

## Overview
Stand up `gluon-contract` (gluon PLAN.md RUST-1.1, ADR 0028 decision 3): a
Python + pytest project with its conductor setup, CI and a public remote,
ready for the isolated-mode runner (RUST-1.2) and the check groups after it.
No contract checks yet.

## Functional Requirements
1. **Project:** uv-managed Python 3.13 project (`pyproject.toml`,
   `.python-version`, committed `uv.lock`), `uv_build` backend, `src/` layout
   with package `gluon_contract`. Dev tools pinned exactly: pytest 9.2.0,
   pytest-cov 7.1.0, ruff 0.17.3, mypy 2.4.1. `.venv/`, caches and coverage
   output gitignored.
2. **Tool config in `pyproject.toml`:** pytest `testpaths = ["tests"]` with
   strict markers and config; coverage over `gluon_contract`, branch coverage,
   fail under 80%; ruff (line length 100, target py313, the rule sets in
   `tech-stack.md`); mypy `strict` over `src/` and `tests/`.
3. **Placeholder unit test:** proves the package imports and reports the
   project's version, so CI has a real test and a coverage figure from day
   one.
4. **Conductor:** `/conductor:setup` equivalent with the standard
   `workflow.md` (commands adapted to uv), `python.md` + `general.md`
   styleguides, and the backlog seeded with the remaining PLAN items this repo
   owns (RUST-1.2–1.9, 5.0, 5.4, 6.1, 6.5), one track per item.
5. **CI:** the checks are defined once, in `scripts/ci.sh` (`uv sync
   --locked`, `ruff format --check`, `ruff check`, `mypy`, `pytest` with the
   coverage gate). The sandbox runs it directly; GitHub Actions (setup-uv, uv
   pinned) runs the same script. No Docker, no cluster.
6. **Remote:** public `beckfordp/gluon-contract`, pushed; Actions green.
   *(2026-11-08: deferred — the sandbox, where this work is tested, has no
   GitHub access. `scripts/ci.sh` green in the sandbox is the gate meanwhile.)*
7. **README:** purpose, prerequisites (uv; PostgreSQL 16 binaries for
   later checks), commands, links to ADR 0028 and PLAN.md "Rust Spike".
8. **gluon:** `tests/README.md` lists the new repo.

## Non-Functional Requirements
- `uv sync --locked` fails on a stale lock
- A bare `uv run pytest` never starts processes or touches the network

## Acceptance Criteria
- `uv run ruff format --check && uv run ruff check && uv run mypy && uv run
  pytest` green locally, coverage ≥ 80%
- `scripts/ci.sh` green in the sandbox from a clean checkout (no `.venv`)
- *(deferred)* the same script green in GitHub Actions on the public remote
- Breaking the placeholder test fails `pytest` with a readable assertion

## Out of Scope
- Config for targets and modes, processes, stubs, `contracts/` (RUST-1.2)
- Any contract check (RUST-1.3 onwards)
