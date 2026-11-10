# SPDX-License-Identifier: MIT

"""Process inspection for integration tests."""

import subprocess


def processes_mentioning(text: str) -> list[int]:
    """PIDs whose command line contains `text` (to prove nothing was left running).

    From `ps -A -o pid=,command=`, which procps (Linux) and BSD ps (macOS) both
    answer the same way: one process per line, its pid then its command line.
    """
    listing = subprocess.run(
        ["ps", "-A", "-o", "pid=,command="], capture_output=True, text=True, check=True
    ).stdout
    pids = []
    for line in listing.splitlines():
        pid, _, command = line.strip().partition(" ")
        if text in command:
            pids.append(int(pid))
    return pids
