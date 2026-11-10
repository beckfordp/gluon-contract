#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# The CI checks, defined once: GitHub Actions runs this script, and so does the
# sandbox, which has no GitHub access. Unit tests only (testpaths = ["tests"]);
# the contract checks under checks/ are never part of CI.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

uv sync --locked              # fails if uv.lock is stale against pyproject.toml
uv run ruff format --check
uv run ruff check
uv run mypy                   # src/ and tests/ (pyproject.toml)
uv run mypy checks            # separately: its conftest.py would clash with tests/
uv run pytest --cov           # coverage gate from pyproject.toml (80%)
