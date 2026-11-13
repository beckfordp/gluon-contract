# SPDX-License-Identifier: MIT

"""Every check names its source, and every capture file it cites exists (gluon TD-41)."""

from pathlib import Path

import pytest

from gluon_contract.check_sources import cited_files, source_problems
from gluon_contract.contracts import CONTRACTS_ROOT, latest_capture

CHECKS = Path(__file__).resolve().parents[2] / "checks"
MODULE = '''
import pytest

pytestmark = pytest.mark.service("user-service")


def test_x(harness):
    """What it checks.

    Source: capture {cited}.
    """
'''


@pytest.mark.parametrize(
    ("docstring", "files"),
    [
        ("Source: capture http/a.txt.", ["http/a.txt"]),
        ("Source: capture http/a.txt and http/b.txt.", ["http/a.txt", "http/b.txt"]),
        # A bare name after a path is in that path's directory: the names TD-41 found unchecked
        ("Source: capture http/a.txt, b.txt, c.txt.", ["http/a.txt", "http/b.txt", "http/c.txt"]),
        ("Source: capture http/a.txt and b.txt.", ["http/a.txt", "http/b.txt"]),
        (
            "Source: capture http/a.txt, b.txt, asyncapi-html/index.html",
            ["http/a.txt", "http/b.txt", "asyncapi-html/index.html"],
        ),
        ("Source: capture openapi.yaml and http/*.txt (ADR 0028)", ["openapi.yaml", "http/*.txt"]),
        ("Source: capture asyncapi-html/ (css/, js/).", ["asyncapi-html/"]),
        ("Source: ADR 0025; capture stdout.log, a span", ["stdout.log"]),
        ("Source: application.conf;\ncapture metrics.txt\n(the counter).", ["metrics.txt"]),
        ("Source: capture http/<captured>.txt, each answer", []),
        ("Source: the capture has no GET headers.", []),
        ("Source: debezium-connectors-register.yaml (user-outbox-connector)", []),
        ("Compares capture http/a.txt.\n\nSource: ADR 0028.", []),
        ("Source: ADR 0028.\n\nThe capture http/a.txt is the same.", []),
    ],
)
def test_the_files_a_source_line_cites(docstring: str, files: list[str]) -> None:
    """Names after `capture` in the Source: paragraph, relative to the capture."""
    assert cited_files(docstring) == files


@pytest.fixture
def capture(tmp_path: Path) -> Path:
    (tmp_path / "http").mkdir()
    (tmp_path / "http" / "a.txt").write_text("")
    (tmp_path / "asyncapi-html").mkdir()
    return tmp_path


@pytest.mark.parametrize(
    "cited", ["http/a.txt", "http/*.txt", "asyncapi-html/", "http/<captured>.txt"]
)
def test_a_check_citing_what_the_capture_holds_is_fine(capture: Path, cited: str) -> None:
    source = MODULE.format(cited=cited)
    assert source_problems("checks/test_x.py", source, lambda _: capture) == []


@pytest.mark.parametrize(
    ("cited", "missing"),
    [
        ("http/a.txt, missing.txt", "http/missing.txt"),
        ("http/missing.txt and http/a.txt", "http/missing.txt"),
        ("http/*.json", "http/*.json"),
        ("css/", "css/"),
        ("http/a.txt/", "http/a.txt/"),
    ],
)
def test_a_citation_the_capture_lacks_is_a_problem(capture: Path, cited: str, missing: str) -> None:
    """Every name, not only the first `http/<name>.txt` (TD-41)."""
    source = MODULE.format(cited=cited)
    assert source_problems("checks/test_x.py", source, lambda _: capture) == [
        f"checks/test_x.py::test_x cites {missing}, which user-service's capture "
        f"{capture.name} lacks"
    ]


def test_a_check_without_a_source_line_is_a_problem(capture: Path) -> None:
    source = (
        'pytestmark = pytest.mark.service("user-service")\n\ndef test_y():\n    """No source."""'
    )
    assert source_problems("checks/test_x.py", source, lambda _: capture) == [
        "checks/test_x.py::test_y: no Source: line"
    ]


def test_only_checks_are_read(capture: Path) -> None:
    """Helpers and fixtures need no Source: line."""
    source = 'pytestmark = pytest.mark.service("user-service")\n\ndef helper():\n    pass'
    assert source_problems("checks/support.py", source, lambda _: capture) == []


def test_each_service_a_module_is_marked_for_is_checked(tmp_path: Path) -> None:
    """A module marked for two services cites files both captures hold."""
    holds, lacks = tmp_path / "holds", tmp_path / "lacks"
    (holds / "http").mkdir(parents=True)
    (holds / "http" / "a.txt").write_text("")
    lacks.mkdir()
    source = MODULE.format(cited="http/a.txt").replace(
        '"user-service"', '"user-service", "notification-service"'
    )
    captures = {"user-service": holds, "notification-service": lacks}
    assert source_problems("checks/test_x.py", source, captures.__getitem__) == [
        "checks/test_x.py::test_x cites http/a.txt, which notification-service's capture "
        "lacks lacks"
    ]


def test_every_check_in_checks_names_its_source_and_cites_what_exists() -> None:
    """CI's guard (was verify-check-group.sh section 2)."""
    modules = sorted(CHECKS.glob("test_*.py"))
    assert modules
    problems = [
        problem
        for path in modules
        for problem in source_problems(
            f"checks/{path.name}",
            path.read_text(encoding="utf-8"),
            lambda service: latest_capture(CONTRACTS_ROOT, service),
        )
    ]
    assert problems == []
