# SPDX-License-Identifier: MIT

"""One helper per job: no check module redefines a shared one (gluon TD-34)."""

from pathlib import Path

import pytest

from gluon_contract.shared_helpers import defined_names, redefinition_problems

ROOT = Path(__file__).resolve().parents[2]
CHECKS = ROOT / "checks"
SHARED = ("checks/support.py", "src/gluon_contract/expect.py")


@pytest.mark.parametrize(
    ("source", "names"),
    [
        ("def new_email() -> str:\n    return ''", {"new_email"}),
        ('JSON = {"Content-Type": "application/json"}', {"JSON"}),
        ("TEXT_PLAIN: str = 'text/plain'", {"TEXT_PLAIN"}),
        ("class Row:\n    pass", {"Row"}),
        ("type Db = int", {"Db"}),
        ("A, B = 1, 2", {"A", "B"}),
        ("def _head() -> None:\n    pass", set()),
        ("pytestmark = pytest.mark.cluster", set()),
        ("from support import JSON, new_email", set()),
        ("def f() -> None:\n    JSON = 1", {"f"}),
    ],
)
def test_the_names_a_module_defines(source: str, names: set[str]) -> None:
    """Top-level public definitions only: not imports, private names, pytestmark or locals."""
    assert defined_names(source) == names


def test_a_check_module_redefining_a_shared_helper_is_a_problem() -> None:
    """Each redefinition names the module, the helper and where it already lives."""
    shared = {"checks/support.py": "def new_email() -> str:\n    return ''\nJSON = {}"}
    modules = {
        "checks/test_x.py": "JSON = {}\ndef new_email() -> str:\n    return ''",
        "checks/test_y.py": "from support import JSON, new_email",
    }
    assert redefinition_problems(shared, modules) == [
        "checks/test_x.py defines JSON, which checks/support.py already does: import it",
        "checks/test_x.py defines new_email, which checks/support.py already does: import it",
    ]


def test_no_check_module_redefines_a_shared_helper() -> None:
    """CI's guard: support.py's and expect.py's helpers are defined once."""
    shared = {name: (ROOT / name).read_text(encoding="utf-8") for name in SHARED}
    modules = {
        f"checks/{path.name}": path.read_text(encoding="utf-8")
        for path in sorted(CHECKS.glob("*.py"))
        if f"checks/{path.name}" not in shared
    }
    assert modules
    assert redefinition_problems(shared, modules) == []
