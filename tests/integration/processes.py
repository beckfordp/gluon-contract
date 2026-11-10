# SPDX-License-Identifier: MIT

"""Process inspection for integration tests."""

from pathlib import Path


def processes_mentioning(text: str) -> list[int]:
    """PIDs whose command line contains `text` (to prove nothing was left running)."""
    pids = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            cmdline = (proc / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
        except OSError:
            continue
        if text in cmdline:
            pids.append(int(proc.name))
    return pids
