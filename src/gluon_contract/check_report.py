# SPDX-License-Identifier: MIT

"""Each check's outcome and reason, read from a run's junit report (gluon TD-40).

`scripts/verify-check-group.sh` used pytest's `-rA` summary, which cuts a failure's
message to the terminal width or drops it. The junit report (`--junitxml`) has every
message whole; this reads it into one `Outcome` per check and the lines the script
prints.
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

type State = Literal["passed", "failed", "error", "skipped"]

RED_TAGS: dict[str, State] = {"failure": "failed", "error": "error", "skipped": "skipped"}
"""A testcase's child element, by its tag, and the state it means; none means passed."""
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
    """`pass <name>`, or `red  <name> - <reason>` (one line, at most REASON_LENGTH);
    None for a skip, which isn't this run's outcome."""
    if outcome.state == "skipped":
        return None
    if outcome.state == "passed":
        return f"pass {outcome.name}"
    reason = _one_line(outcome.reason)
    return f"red  {outcome.name}" + (f" - {reason}" if reason else "")


def _outcome(case: ET.Element) -> Outcome:
    name = case.get("name", "")
    for tag, state in RED_TAGS.items():
        element = case.find(tag)
        if element is not None:
            return Outcome(name, state, element.get("message", ""))
    return Outcome(name, "passed", "")


def _one_line(reason: str) -> str:
    text = re.sub(r"\s+", " ", reason).strip()
    return text if len(text) <= REASON_LENGTH else text[: REASON_LENGTH - 1] + "…"
