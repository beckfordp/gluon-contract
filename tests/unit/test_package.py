# SPDX-License-Identifier: MIT

"""The package imports and reports the project's version."""

import tomllib
from pathlib import Path

import gluon_contract

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def test_version_matches_pyproject() -> None:
    """`gluon_contract.__version__` is the version declared in pyproject.toml."""
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    assert gluon_contract.__version__ == project["version"]
