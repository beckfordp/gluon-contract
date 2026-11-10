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
