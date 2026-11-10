# SPDX-License-Identifier: MIT

"""`contracts/`: Scala-generated artifacts and captures, each with its provenance (spec FR9).

Layout: contracts/<service>/<capture>/ with a PROVENANCE.md in every capture
directory (who ran what, where, the user-service commit). Files directly under
contracts/<service>/, such as CAPTURE.md, are instructions, not captures.
"""

from pathlib import Path

import pytest

from gluon_contract.contracts import (
    CONTRACTS_ROOT,
    ContractsError,
    capture_dirs,
    latest_capture,
)


def capture(root: Path, service: str, name: str, *, provenance: bool = True) -> Path:
    """A capture directory, with or without its PROVENANCE.md."""
    directory = root / service / name
    directory.mkdir(parents=True)
    if provenance:
        (directory / "PROVENANCE.md").write_text("captured on the laptop\n", encoding="utf-8")
    return directory


def test_capture_directories_are_listed_oldest_first(tmp_path: Path) -> None:
    """Dated names sort in capture order; files beside them are not captures."""
    newer = capture(tmp_path, "user-service", "20261110")
    older = capture(tmp_path, "user-service", "20261109")
    (tmp_path / "user-service" / "CAPTURE.md").write_text("commands\n", encoding="utf-8")
    assert capture_dirs(tmp_path, "user-service") == [older, newer]


def test_a_capture_without_provenance_is_an_error(tmp_path: Path) -> None:
    """Every capture says where it came from, or nothing in it can be trusted."""
    capture(tmp_path, "user-service", "20261109")
    capture(tmp_path, "user-service", "20261110", provenance=False)
    with pytest.raises(ContractsError, match=r"20261110.*PROVENANCE\.md"):
        capture_dirs(tmp_path, "user-service")


def test_the_latest_capture_is_the_newest(tmp_path: Path) -> None:
    """Checks read the newest capture."""
    capture(tmp_path, "user-service", "20261109")
    newest = capture(tmp_path, "user-service", "20261110")
    assert latest_capture(tmp_path, "user-service") == newest


def test_no_capture_yet_says_how_to_get_one(tmp_path: Path) -> None:
    """Before the laptop capture arrives, the error points at CAPTURE.md."""
    (tmp_path / "user-service").mkdir()
    with pytest.raises(ContractsError, match=r"no capture .*CAPTURE\.md"):
        latest_capture(tmp_path, "user-service")
    with pytest.raises(ContractsError, match="no capture"):
        latest_capture(tmp_path, "order-service")


def test_every_capture_in_this_repo_has_its_provenance() -> None:
    """The rule holds for what is committed here."""
    assert CONTRACTS_ROOT.is_dir()
    for service in sorted(p for p in CONTRACTS_ROOT.iterdir() if p.is_dir()):
        capture_dirs(CONTRACTS_ROOT, service.name)
