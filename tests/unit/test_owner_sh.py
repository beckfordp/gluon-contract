# SPDX-License-Identifier: MIT

"""scripts/lib/owner.sh: the repo owner, their home and the re-run as them, on Linux and macOS."""

import os
import pwd
import re
import subprocess
from pathlib import Path

import pytest

OWNER_SH = Path(__file__).resolve().parents[2] / "scripts" / "lib" / "owner.sh"
ME = pwd.getpwuid(os.getuid())


def run(snippet: str, path_first: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Runs `snippet` in bash after sourcing owner.sh, with `path_first` ahead on the PATH."""
    env = dict(os.environ)
    if path_first is not None:
        env["PATH"] = f"{path_first}{os.pathsep}{env['PATH']}"
    return subprocess.run(
        ["bash", "-c", f'source "{OWNER_SH}"; {snippet}'],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def stand_in(bin_dir: Path, name: str, body: str) -> Path:
    """Writes an executable stand-in `name` into `bin_dir` running the sh `body`."""
    bin_dir.mkdir(exist_ok=True)
    path = bin_dir / name
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(0o755)
    return bin_dir


def test_repo_owner_is_whoever_owns_the_directory(tmp_path: Path) -> None:
    """With the OS's own `stat`, a directory we made is ours."""
    result = run(f'repo_owner "{tmp_path}"')
    assert (result.returncode, result.stdout.strip()) == (0, ME.pw_name)


def test_repo_owner_uses_gnu_stat_where_there_is_one(tmp_path: Path) -> None:
    """GNU `stat -c %U` (Linux) answers first."""
    bin_dir = stand_in(
        tmp_path / "bin",
        "stat",
        '[ "$1" = -c ] && [ "$2" = %U ] && echo gnu-user && exit 0; exit 1',
    )
    result = run(f'repo_owner "{tmp_path}"', bin_dir)
    assert (result.returncode, result.stdout.strip()) == (0, "gnu-user")


def test_repo_owner_falls_back_to_bsd_stat(tmp_path: Path) -> None:
    """BSD `stat` (macOS) rejects `-c`; `stat -f %Su` answers instead."""
    bin_dir = stand_in(
        tmp_path / "bin",
        "stat",
        '[ "$1" = -f ] && [ "$2" = %Su ] && echo bsd-user && exit 0; exit 1',
    )
    result = run(f'repo_owner "{tmp_path}"', bin_dir)
    assert (result.returncode, result.stdout.strip()) == (0, "bsd-user")


def test_owner_home_of_the_current_user() -> None:
    """With the OS's own tools, our home is the one in the password database."""
    result = run(f"owner_home {ME.pw_name}")
    assert (result.returncode, result.stdout.strip()) == (0, ME.pw_dir)


def test_owner_home_uses_getent_where_it_answers(tmp_path: Path) -> None:
    """`getent passwd` (Linux) gives the home: its sixth field."""
    bin_dir = stand_in(tmp_path / "bin", "getent", "echo 'u:x:1:1::/custom/home:/bin/sh'")
    result = run("owner_home u", bin_dir)
    assert (result.returncode, result.stdout.strip()) == (0, "/custom/home")


def test_owner_home_falls_back_without_getent(tmp_path: Path) -> None:
    """Where `getent` gives nothing (macOS has none), `~user` gives the home."""
    bin_dir = stand_in(tmp_path / "bin", "getent", "exit 2")
    result = run(f"owner_home {ME.pw_name}", bin_dir)
    assert (result.returncode, result.stdout.strip()) == (0, ME.pw_dir)


def test_owner_home_refuses_a_name_that_is_not_a_user_name(tmp_path: Path) -> None:
    """A name outside [A-Za-z0-9._-] is refused (exit 2) before any expansion runs it."""
    marker = tmp_path / "ran"
    bin_dir = stand_in(tmp_path / "bin", "getent", "exit 2")
    result = run(f"owner_home 'a;touch {marker}'", bin_dir)
    assert result.returncode == 2
    assert not marker.exists()


def test_run_as_owner_carries_on_for_the_owner(tmp_path: Path) -> None:
    """The repo's owner runs the script as it is: return 0, nothing printed."""
    result = run(f'run_as_owner "{tmp_path}" /no/such/script; echo carried-on')
    assert (result.returncode, result.stdout, result.stderr) == (0, "carried-on\n", "")


@pytest.mark.skipif(os.getuid() == 0, reason="as root it re-runs as the owner instead")
def test_run_as_owner_stops_anyone_else(tmp_path: Path) -> None:
    """Anyone but the owner, without root, is told who to run it as (exit 1)."""
    bin_dir = stand_in(tmp_path / "bin", "stat", "echo someone-else")
    result = run(f'run_as_owner "{tmp_path}" /no/such/script; echo carried-on', bin_dir)
    assert result.returncode == 1
    assert result.stdout == f"FAIL run as someone-else, who owns {tmp_path}\n"


def test_no_script_calls_a_gnu_or_linux_only_command_itself() -> None:
    """owner.sh holds the fallbacks for `stat -c`, `getent` and /proc; other scripts use it
    (gluon TD-46)."""
    scripts = sorted(p for p in OWNER_SH.parents[1].rglob("*.sh") if p != OWNER_SH)
    assert scripts
    calls = [
        f"{path.name}:{number}: {line.strip()}"
        for path in scripts
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if re.search(r"stat -c|getent|/proc/", line) and not line.lstrip().startswith("#")
    ]
    assert calls == []
