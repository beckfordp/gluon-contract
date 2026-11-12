# SPDX-License-Identifier: MIT

"""Which service each check module judges, read from its source (RPN-3 review R16, R18).

A check module declares its service with a module-level
`pytestmark = pytest.mark.service("<name>", ...)` (alone or in a list). The pytest
plugin deselects it in a run for another service; an unmarked module would run
in every service's run, so every module in `checks/` must carry one naming
known services (`services.KNOWN_SERVICES`). A check that really is
service-neutral names every service. Read with `ast`, so nothing is imported.
"""

import ast
from collections.abc import Mapping
from typing import TypeGuard

from gluon_contract.services import KNOWN_SERVICES

NOT_A_STRING = "<not a string>"
"""Stands for a marker argument that isn't a string literal (a name, an expression)."""


def module_services(source: str) -> tuple[str, ...] | None:
    """The services a module's `pytestmark` names, or None if it has no service marker."""
    for node in ast.parse(source).body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "pytestmark" for target in node.targets
        ):
            continue
        values = node.value.elts if isinstance(node.value, ast.List | ast.Tuple) else [node.value]
        for value in values:
            if _is_service_marker(value):
                return tuple(_literal(argument) for argument in value.args)
    return None


def marker_problems(sources: Mapping[str, str]) -> list[str]:
    """One line per module (by name, its source given) without a good service marker."""
    problems = []
    for name, source in sources.items():
        services = module_services(source)
        if services is None:
            problems.append(f"{name}: no module-level pytest.mark.service(...)")
        elif not services or not set(services) <= set(KNOWN_SERVICES):
            problems.append(
                f"{name}: service marker names {services!r}; it must name known services "
                f"({', '.join(KNOWN_SERVICES)})"
            )
    return problems


def _is_service_marker(node: ast.expr) -> TypeGuard[ast.Call]:
    """`pytest.mark.service(...)`."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "service"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "mark"
        and isinstance(node.func.value.value, ast.Name)
        and node.func.value.value.id == "pytest"
    )


def _literal(node: ast.expr) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return NOT_A_STRING
