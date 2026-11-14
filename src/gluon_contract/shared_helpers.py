# SPDX-License-Identifier: MIT

"""One helper per job: a shared helper is imported, never written out again.

The shared helpers are the public top-level names of `checks/support.py` (requests and
throwaway data) and `gluon_contract.expect` (response comparisons): two copies of a
comparison rule drift, so CI fails when a check module defines one of those names
again (gluon TD-34). Postgres is reached only through `gluon_contract.postgres.connect`
(TD-35). Read with `ast`, so nothing is imported.
"""

import ast
from collections.abc import Mapping
from typing import TypeGuard

IGNORED = frozenset({"pytestmark"})
"""Names every check module defines for itself."""
CONNECT_MODULE = "src/gluon_contract/postgres.py"
"""Where the one call of `psycopg.connect` lives, in its `connect`."""


def defined_names(source: str) -> set[str]:
    """The public names a module defines at top level (functions, classes, constants,
    type aliases); imports don't count."""
    names: set[str] = set()
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.TypeAlias) and isinstance(node.name, ast.Name):
            names.add(node.name.id)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                names |= _target_names(target)
        elif isinstance(node, ast.AnnAssign):
            names |= _target_names(node.target)
    return {name for name in names if not name.startswith("_") and name not in IGNORED}


def redefinition_problems(shared: Mapping[str, str], modules: Mapping[str, str]) -> list[str]:
    """One line per name a module (by name, its source given) defines that a shared
    module already does."""
    owners = {name: owner for owner, source in shared.items() for name in defined_names(source)}
    return [
        f"{module} defines {name}, which {owners[name]} already does: import it"
        for module, source in modules.items()
        for name in sorted(defined_names(source) & owners.keys())
    ]


def connect_problems(sources: Mapping[str, str]) -> list[str]:
    """One line per call of `psycopg.connect` in a module (by path, its source given)
    other than the one inside `gluon_contract.postgres.connect`."""
    problems = []
    for module, source in sources.items():
        tree = ast.parse(source)
        allowed: set[int] = set()
        if module == CONNECT_MODULE:
            for node in tree.body:
                if isinstance(node, ast.FunctionDef) and node.name == "connect":
                    allowed |= {id(call) for call in ast.walk(node)}
        problems += [
            f"{module}:{node.lineno} calls psycopg.connect: use gluon_contract.postgres.connect"
            for node in ast.walk(tree)
            if _is_psycopg_connect(node) and id(node) not in allowed
        ]
    return problems


def _is_psycopg_connect(node: ast.AST) -> TypeGuard[ast.Call]:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "connect"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "psycopg"
    )


def _target_names(target: ast.expr) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, ast.Tuple | ast.List):
        return {name for element in target.elts for name in _target_names(element)}
    return set()
