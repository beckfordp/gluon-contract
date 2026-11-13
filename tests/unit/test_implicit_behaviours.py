# SPDX-License-Identifier: MIT

"""docs/implicit-behaviours.md names only checks that exist (was verify-implicit-behaviours.sh)."""

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LIST = REPO / "docs" / "implicit-behaviours.md"


def checks_in(module: Path) -> set[str]:
    """The module-level test functions in a check module."""
    tree = ast.parse(module.read_text(encoding="utf-8"))
    return {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}


def test_every_check_the_list_names_exists() -> None:
    """A `module.py::test_name` reference resolves under checks/ (or from the repo root)."""
    refs = sorted(set(re.findall(r"`([a-z_/]+\.py)::(test_[a-z0-9_]+)`", LIST.read_text())))
    assert refs
    missing = []
    for file, name in refs:
        module = REPO / "checks" / file
        if not module.is_file():
            module = REPO / file
        if not module.is_file() or name not in checks_in(module):
            missing.append(f"{file}::{name}")
    assert missing == []
