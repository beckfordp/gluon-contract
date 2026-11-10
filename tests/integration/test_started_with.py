# SPDX-License-Identifier: MIT

"""The stand-in reports the environment exactly as its process was started with it."""

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Prints started_with() as JSON, from a process whose environment is only `GIVEN`.
REPORT = (
    "import json, sys\n"
    f"sys.path.insert(0, {str(HERE)!r})\n"
    "from stand_in_target import started_with\n"
    "print(json.dumps(started_with()))\n"
)


def test_started_with_is_exactly_the_environment_given() -> None:
    """In the C locale Python adds LC_CTYPE to os.environ (PEP 538); started_with() doesn't."""
    given = {"LANG": "C", "PLAIN": "value", "SPACED": "a b", "EMPTY": ""}
    result = subprocess.run(
        [sys.executable, "-c", REPORT],
        env=given,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == given
