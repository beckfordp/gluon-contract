# SPDX-License-Identifier: MIT

"""Each check's outcome and reason, read from a run's junit report (gluon TD-40).

The samples are pytest's own junit XML (`--junitxml`, `-o junit_logging=no`), as
`scripts/verify-check-group.sh` writes it.
"""

from pathlib import Path

import pytest

from gluon_contract.check_report import (
    REASON_LENGTH,
    CheckReportError,
    Outcome,
    line,
    outcomes,
)

REPORT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites name="pytest tests"><testsuite name="pytest" tests="4">
<testcase classname="checks.test_x" name="test_ok" time="0.000" />
<testcase classname="checks.test_x" name="test_red[HEAD-emails-head]" time="0.000">
<failure message="AssertionError: got 404&#10;    expected 200&#10;assert 404 == 200">trace
E       AssertionError: got 404</failure></testcase>
<testcase classname="checks.test_x" name="test_err" time="0.000">
<error message="failed on setup with &quot;RuntimeError: no harness&quot;">trace</error>
</testcase>
<testcase classname="checks.test_x" name="test_skip" time="0.000">
<skipped type="pytest.skip" message="cluster only">where</skipped></testcase>
</testsuite></testsuites>
"""


def report(tmp_path: Path, text: str = REPORT) -> Path:
    """`text` written as a run's report."""
    path = tmp_path / "run.xml"
    path.write_text(text, encoding="utf-8")
    return path


def test_each_check_has_its_state_and_reason(tmp_path: Path) -> None:
    """In report order, the name with its parameters; the reason is the message pytest
    gives the failure, error or skip."""
    assert outcomes(report(tmp_path)) == [
        Outcome("test_ok", "passed", ""),
        Outcome(
            "test_red[HEAD-emails-head]",
            "failed",
            "AssertionError: got 404\n    expected 200\nassert 404 == 200",
        ),
        Outcome("test_err", "error", 'failed on setup with "RuntimeError: no harness"'),
        Outcome("test_skip", "skipped", "cluster only"),
    ]


def test_a_red_line_carries_its_reason_on_one_line(tmp_path: Path) -> None:
    """Whitespace collapsed, so a multi-line assert message reads as one line."""
    red = outcomes(report(tmp_path))[1]
    assert line(red) == (
        "red  test_red[HEAD-emails-head] - AssertionError: got 404 expected 200 assert 404 == 200"
    )


def test_a_long_reason_is_cut_with_an_ellipsis() -> None:
    """At REASON_LENGTH characters, the last one `…`."""
    long = line(Outcome("test_long", "failed", "x" * 500))
    assert long is not None
    reason = long.removeprefix("red  test_long - ")
    assert len(reason) == REASON_LENGTH
    assert reason == "x" * (REASON_LENGTH - 1) + "…"


def test_an_error_is_red_and_a_pass_is_green() -> None:
    """Pass lines carry no reason; an error reads as a red line, as a failure does."""
    assert line(Outcome("test_ok", "passed", "")) == "pass test_ok"
    assert line(Outcome("test_err", "error", "boom")) == "red  test_err - boom"


def test_a_skip_has_no_line() -> None:
    """Skipped checks aren't this run's outcome (cluster-only, isolated-only): no line."""
    assert line(Outcome("test_skip", "skipped", "cluster only")) is None


def test_a_red_check_without_a_message_has_no_dash() -> None:
    """A failure pytest gave no message keeps the bare name."""
    assert line(Outcome("test_red", "failed", "")) == "red  test_red"


@pytest.mark.parametrize("text", [None, "<testsuites><testcase"], ids=["missing", "garbled"])
def test_an_unreadable_report_is_an_error_naming_it(tmp_path: Path, text: str | None) -> None:
    """Never an empty pass: a run without a readable report has no outcomes to show."""
    path = tmp_path / "run.xml" if text is None else report(tmp_path, text)
    with pytest.raises(CheckReportError, match=r"run\.xml"):
        outcomes(path)
