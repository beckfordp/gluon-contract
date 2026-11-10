# SPDX-License-Identifier: MIT

"""processes_mentioning finds live processes by their command line, on any OS."""

import subprocess
import sys
import uuid

from processes import processes_mentioning


def test_a_running_process_is_found_and_a_stopped_one_is_not() -> None:
    """A process whose arguments contain a marker is listed until it has stopped."""
    marker = f"processes-marker-{uuid.uuid4().hex}"
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", marker])
    try:
        assert processes_mentioning(marker) == [child.pid]
    finally:
        child.kill()
        child.wait()
    assert processes_mentioning(marker) == []


def test_nothing_is_found_for_text_no_process_mentions() -> None:
    """Text in no command line (and not in the listing command's own) finds nothing."""
    assert processes_mentioning(f"no-such-process-{uuid.uuid4().hex}") == []
