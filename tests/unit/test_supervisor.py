# SPDX-License-Identifier: MIT

"""The supervisor's logs (gluon TD-45), without starting a process."""

from pathlib import Path

from gluon_contract.supervisor import Supervisor


def test_a_log_reads_as_empty_until_written_and_its_tail_is_the_last_lines(
    tmp_path: Path,
) -> None:
    """`text` is '' and `tail` says so before the process writes anything."""
    supervisor = Supervisor(tmp_path)
    assert supervisor.text("x.log") == ""
    assert supervisor.tail("x.log") == "(no log)"
    (tmp_path / "x.log").write_text("".join(f"line {n}\n" for n in range(30)))
    assert supervisor.tail("x.log").splitlines() == [f"line {n}" for n in range(10, 30)]
