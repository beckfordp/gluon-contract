# SPDX-License-Identifier: MIT

"""Every check module says which service's contract it is (RPN-3 review R16, R18)."""

from pathlib import Path

import pytest

from gluon_contract.check_markers import marker_problems, module_services

CHECKS = Path(__file__).resolve().parents[2] / "checks"


@pytest.mark.parametrize(
    ("source", "services"),
    [
        ('pytestmark = pytest.mark.service("user-service")', ("user-service",)),
        (
            'pytestmark = [pytest.mark.service("notification-service"), pytest.mark.cluster]',
            ("notification-service",),
        ),
        (
            'pytestmark = pytest.mark.service("user-service", "notification-service")',
            ("user-service", "notification-service"),
        ),
        ("pytestmark = pytest.mark.cluster", None),
        ("def test_x():\n    pass", None),
        ('def test_x():\n    pytestmark = pytest.mark.service("user-service")', None),
    ],
)
def test_the_services_a_module_is_marked_for(source: str, services: tuple[str, ...] | None) -> None:
    """Read from the module-level `pytestmark` only, without importing the module."""
    assert module_services(source) == services


def test_an_unmarked_module_is_a_problem() -> None:
    """A check module without a service marker would run in every service's run."""
    assert marker_problems({"checks/test_x.py": "def test_x():\n    pass"}) == [
        "checks/test_x.py: no module-level pytest.mark.service(...)"
    ]


@pytest.mark.parametrize(
    ("source", "named"),
    [
        ('pytestmark = pytest.mark.service("user-servce")', "('user-servce',)"),
        ("pytestmark = pytest.mark.service()", "()"),
        ("pytestmark = pytest.mark.service(SERVICE)", "('<not a string>',)"),
    ],
)
def test_a_marker_naming_no_known_service_is_a_problem(source: str, named: str) -> None:
    """Misspelt, empty, or not a literal: the marker must name known services."""
    (problem,) = marker_problems({"checks/test_x.py": source})
    assert problem.startswith(f"checks/test_x.py: service marker names {named}")
    assert "user-service, notification-service" in problem


def test_every_module_in_checks_is_marked_for_a_known_service() -> None:
    """CI's guard: each checks/test_*.py belongs to a known service."""
    modules = sorted(CHECKS.glob("test_*.py"))
    assert modules
    sources = {f"checks/{path.name}": path.read_text(encoding="utf-8") for path in modules}
    assert marker_problems(sources) == []
