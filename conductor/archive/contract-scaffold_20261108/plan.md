# Plan — RUST-1.1: Contract harness scaffold

## Phase 1: Project and tooling [checkpoint: a95d9b9]
- [x] Task: conductor setup — product, guidelines, tech stack, workflow (uv commands), `python.md` + `general.md`, tracks with backlog seeded 5885564
- [x] Task: write the failing placeholder test — `tests/test_package.py`: `gluon_contract.__version__` equals the project version in `pyproject.toml` (red: `ModuleNotFoundError: gluon_contract`) 5e82f4a
- [x] Task: project — `pyproject.toml` (uv_build, Python 3.13, pinned dev tools, pytest/coverage/ruff/mypy config), `.python-version`, `.gitignore`, `src/gluon_contract/__init__.py`, `uv.lock`; `ruff format --check`, `ruff check`, `mypy`, `pytest --cov` green (1 passed, 100% coverage); stale lock fails `uv sync --locked`; a broken assertion reads `assert '0.1.0' == '9.9.9'` 5e82f4a
- [x] Task: README (purpose, prerequisites, commands, links to ADR 0028 and PLAN.md); gluon `tests/README.md` lists the repo 120705b
- [x] Task: Conductor - User Manual Verification 'Phase 1: Project and tooling' (Protocol in workflow.md)

## Phase 2: CI and remote [checkpoint: afc622b]
- [x] Task: CI defined once in `scripts/ci.sh` (`uv sync --locked`, format check, lint, mypy, pytest with coverage gate); `.github/workflows/ci.yml` (setup-uv) runs that script; `scripts/ci.sh` green in the sandbox from a deleted `.venv` d6de79a
- [x] Task: ~~create public `beckfordp/gluon-contract`, push; Actions green~~ — moved to gluon PLAN.md RUST-5.6 (laptop pass): the sandbox has no GitHub access
- [x] Task: Conductor - User Manual Verification 'Phase 2: CI and remote' (Protocol in workflow.md)
