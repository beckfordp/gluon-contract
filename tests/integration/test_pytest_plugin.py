# SPDX-License-Identifier: MIT

"""Wiring for `checks/`: pytest options and a session `harness` fixture (spec FR8).

Proven with pytester: a throwaway check suite, using the same conftest as
`checks/`, runs against the stand-in target.
"""

import shutil
import sys
from pathlib import Path

import pytest
from processes import processes_mentioning

STAND_IN = Path(__file__).with_name("stand_in_target.py")
STAND_IN_CMD = f"{sys.executable} {STAND_IN}"
CHECKS_CONFTEST = (Path(__file__).parents[2] / "checks" / "conftest.py").read_text
PROBE = """
import urllib.request
from pathlib import Path


def test_ready(harness):
    Path({record!r}).write_text(str(harness.work_dir))
    with urllib.request.urlopen(harness.base_url + "/health/ready") as response:
        assert response.status == 200
"""


def suite(pytester: pytest.Pytester, record: Path) -> None:
    """A one-check suite wired exactly like checks/, recording its work directory."""
    pytester.makeconftest(CHECKS_CONFTEST())
    pytester.makepyfile(test_probe=PROBE.format(record=str(record)))


def test_a_check_gets_a_ready_harness_and_everything_stops(
    pytester: pytest.Pytester, tmp_path: Path
) -> None:
    """--target-cmd starts the world for the session; it is gone afterwards."""
    record = tmp_path / "work_dir.txt"
    suite(pytester, record)
    result = pytester.runpytest("--target-cmd", STAND_IN_CMD, "--target-name", "stand-in")
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["gluon-contract: target stand-in*user-service*"])
    work_dir = Path(record.read_text())
    assert not work_dir.exists()
    assert processes_mentioning(str(work_dir)) == []
    assert processes_mentioning(str(STAND_IN)) == []


def test_contract_variables_work_and_options_win(
    pytester: pytest.Pytester, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CONTRACT_* settings apply; a command-line option overrides its variable."""
    monkeypatch.setenv("CONTRACT_TARGET_CMD", STAND_IN_CMD)
    monkeypatch.setenv("CONTRACT_TARGET_NAME", "from-env")
    suite(pytester, tmp_path / "work_dir.txt")
    result = pytester.runpytest("--target-name", "from-option")
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["gluon-contract: target from-option*"])


def test_keep_artifacts_leaves_the_work_directory(
    pytester: pytest.Pytester, tmp_path: Path
) -> None:
    """--keep-artifacts keeps logs and data for inspection."""
    record = tmp_path / "work_dir.txt"
    suite(pytester, record)
    result = pytester.runpytest("--target-cmd", STAND_IN_CMD, "--keep-artifacts")
    result.assert_outcomes(passed=1)
    work_dir = Path(record.read_text())
    try:
        assert (work_dir / "target.log").is_file()
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def test_an_unusable_configuration_stops_the_run_with_every_problem(
    pytester: pytest.Pytester, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No target command: a usage error naming what to set, not one error per check."""
    monkeypatch.delenv("CONTRACT_TARGET_CMD", raising=False)
    suite(pytester, tmp_path / "work_dir.txt")
    result = pytester.runpytest("--target-cwd", str(tmp_path / "missing"))
    assert result.ret == pytest.ExitCode.USAGE_ERROR
    output = result.stdout.str() + result.stderr.str()
    assert "CONTRACT_TARGET_CMD is required" in output
    assert "CONTRACT_TARGET_CWD is not a directory" in output


SERVICE_SUITE = {
    "test_user": """
import pytest

pytestmark = pytest.mark.service("user-service")


def test_user_contract():
    pass
""",
    "test_notification": """
import pytest

pytestmark = pytest.mark.service("notification-service")


def test_notification_contract():
    pass
""",
    "test_neutral": """
def test_any_service():
    pass
""",
}


def service_suite(pytester: pytest.Pytester) -> None:
    """Checks for user-service, for notification-service, and one for any service; none
    asks for the harness, so nothing is started."""
    pytester.makeconftest(CHECKS_CONFTEST())
    pytester.makepyfile(**SERVICE_SUITE)


def test_a_run_is_for_user_service_by_default(pytester: pytest.Pytester) -> None:
    """No --service: user-service's checks and the neutral one run; the others are
    deselected, not skipped (they aren't this run's contract). With --strict-markers,
    as checks/ runs (pyproject.toml): the conftest registers the service marker."""
    service_suite(pytester)
    result = pytester.runpytest("-v", "--strict-markers")
    result.assert_outcomes(passed=2, deselected=1)
    result.stdout.fnmatch_lines(["*test_any_service PASSED*", "*test_user_contract PASSED*"])
    result.stdout.no_fnmatch_line("*test_notification_contract*")


def test_service_selects_the_checks_marked_for_it(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--service notification-service: its checks and the neutral one; CONTRACT_SERVICE too."""
    service_suite(pytester)
    result = pytester.runpytest("-v", "--service", "notification-service")
    result.assert_outcomes(passed=2, deselected=1)
    result.stdout.fnmatch_lines(["*test_notification_contract PASSED*"])
    result.stdout.no_fnmatch_line("*test_user_contract*")
    monkeypatch.setenv("CONTRACT_SERVICE", "notification-service")
    result = pytester.runpytest("-v")
    result.assert_outcomes(passed=2, deselected=1)
    result.stdout.no_fnmatch_line("*test_user_contract*")


def test_the_report_header_names_the_service(pytester: pytest.Pytester) -> None:
    """The run says which service's contract it judges."""
    service_suite(pytester)
    result = pytester.runpytest(
        "--target-cmd", STAND_IN_CMD, "--target-name", "ns", "--service", "notification-service"
    )
    result.stdout.fnmatch_lines(["gluon-contract: target ns*as notification-service"])


def test_a_service_without_a_profile_stops_the_run_before_any_check(
    pytester: pytest.Pytester,
) -> None:
    """order-service: a usage error naming the services the harness knows; nothing runs."""
    service_suite(pytester)
    result = pytester.runpytest("--target-cmd", STAND_IN_CMD, "--service", "order-service")
    assert result.ret == pytest.ExitCode.USAGE_ERROR
    output = result.stdout.str() + result.stderr.str()
    assert "no profile for 'order-service'" in output
    assert "user-service, notification-service" in output
    result.assert_outcomes()


def test_a_marker_naming_an_unknown_service_is_a_usage_error(pytester: pytest.Pytester) -> None:
    """A misspelt service would deselect its checks everywhere; it stops the run instead."""
    pytester.makeconftest(CHECKS_CONFTEST())
    pytester.makepyfile(
        test_typo="""
import pytest

pytestmark = pytest.mark.service("user-servce")


def test_contract():
    pass
"""
    )
    result = pytester.runpytest()
    assert result.ret == pytest.ExitCode.USAGE_ERROR
    output = result.stdout.str() + result.stderr.str()
    assert "test_typo.py::test_contract" in output
    assert "'user-servce'" in output
