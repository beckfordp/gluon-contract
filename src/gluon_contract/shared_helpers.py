# SPDX-License-Identifier: MIT

"""One helper per job: a check module imports a shared helper, never writes its own (gluon TD-34).

The shared helpers are the public top-level names of `checks/support.py` (requests and
throwaway data) and `gluon_contract.expect` (response comparisons). Two copies of a
comparison rule drift, so CI fails when a check module defines one of those names
again. Read with `ast`, so nothing is imported.
"""

import ast
from collections.abc import Mapping

IGNORED = frozenset({"pytestmark"})
"""Names every check module defines for itself."""


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


def _target_names(target: ast.expr) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, ast.Tuple | ast.List):
        return {name for element in target.elts for name in _target_names(element)}
    return set()
