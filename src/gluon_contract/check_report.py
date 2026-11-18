# SPDX-License-Identifier: MIT

"""Each check's outcome and reason, read from a run's junit report (gluon TD-40).

`scripts/verify-check-group.sh` used pytest's `-rA` summary, which cuts a failure's
message to the terminal width or drops it. The junit report (`--junitxml`) has every
message whole; this reads it into one `Outcome` per check and the lines the script
prints.

    python -m gluon_contract.check_report lines <report>
    python -m gluon_contract.check_report expect-red <report> <reason>
"""

import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from gluon_contract.pending import NOT_YET_IMPLEMENTED

type State = Literal["passed", "failed", "error", "skipped"]

STATE_TAGS: dict[str, State] = {"failure": "failed", "error": "error", "skipped": "skipped"}
"""A testcase's child element, by its tag, and the state it means; none means passed."""
USAGE = (
    "usage: python -m gluon_contract.check_report lines <report>\n"
    "       python -m gluon_contract.check_report expect-red <report> <reason>"
)
REASON_LENGTH = 200
"""The longest reason a line shows, its last character `…` when cut."""


class CheckReportError(Exception):
    """The report is missing or isn't junit XML; the message names it."""


@dataclass(frozen=True, slots=True)
class Outcome:
    """One check: its name (with parameters), state, and the message pytest gave its
    failure, error or skip ('' for a pass)."""

    name: str
    state: State
    reason: str
    text: str = field(default="", compare=False)
    """The failure's text (its traceback); searched by `expect_red`, never shown."""

    @property
    def pending(self) -> bool:
        """A failure saying NOT_YET_IMPLEMENTED (`gluon_contract.pending`): the feature
        isn't built yet. An error or skip saying it isn't pending."""
        return self.state == "failed" and NOT_YET_IMPLEMENTED in self.reason + self.text


def outcomes(path: Path) -> list[Outcome]:
    """Every check in the report, in its order.

    Raises:
        CheckReportError: if the report can't be read as junit XML.
    """
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as error:
        raise CheckReportError(f"no readable junit report at {path}: {error}") from error
    return [_outcome(case) for case in root.iter("testcase")]


def line(outcome: Outcome) -> str | None:
    """`pass <name>`, `red  <name> - <reason>` or, for a pending check, `pend <name> -
    <reason>` (one line, at most REASON_LENGTH); None for a skip, which isn't this run's
    outcome."""
    if outcome.state == "skipped":
        return None
    if outcome.state == "passed":
        return f"pass {outcome.name}"
    reason = _one_line(outcome.reason)
    label = "pend" if outcome.pending else "red "
    return f"{label} {outcome.name}" + (f" - {reason}" if reason else "")


def expect_red(checks: list[Outcome], reason: str) -> list[str]:
    """What stops `checks` being a group written red (`--expect-red`): one problem per
    check that didn't fail, or failed without `reason` in its message or text."""
    if not checks:
        return ["no checks in the report"]
    problems = []
    for check in checks:
        if check.state == "passed":
            problems.append(f"{check.name}: passes")
        elif check.state != "failed":
            problems.append(f"{check.name}: {check.state}")
        elif reason not in check.reason + check.text:
            problems.append(f"{check.name}: fails without {reason!r}: {check.reason[:150]!r}")
    return problems


def main(argv: list[str]) -> int:
    """`lines`: each check's line, then `green=N red=M`. `expect-red`: the problems, or
    `N red`; exit 1 if there are any. Exit 1 for an unreadable report, 2 for a usage
    error."""
    match argv:
        case ["lines", path]:
            command, reason = "lines", ""
        case ["expect-red", path, reason]:
            command = "expect-red"
        case _:
            print(USAGE, file=sys.stderr)
            return 2
    try:
        checks = outcomes(Path(path))
    except CheckReportError as error:
        print(error, file=sys.stderr)
        return 1
    if command == "expect-red":
        problems = expect_red(checks, reason)
        print("\n".join(problems) or f"{len(checks)} red")
        return 1 if problems else 0
    for text in map(line, checks):
        if text is not None:
            print(text)
    green = sum(check.state == "passed" for check in checks)
    red = sum(check.state in ("failed", "error") for check in checks)
    print(f"green={green} red={red}")
    return 0


def _outcome(case: ET.Element) -> Outcome:
    name = case.get("name", "")
    for tag, state in STATE_TAGS.items():
        element = case.find(tag)
        if element is not None:
            return Outcome(name, state, element.get("message", ""), element.text or "")
    return Outcome(name, "passed", "")


def _one_line(reason: str) -> str:
    text = re.sub(r"\s+", " ", reason).strip()
    return text if len(text) <= REASON_LENGTH else text[: REASON_LENGTH - 1] + "…"


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
