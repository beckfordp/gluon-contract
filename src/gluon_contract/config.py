# SPDX-License-Identifier: MIT

"""How a harness run is configured (RUST-1.2 spec FR1).

Settings come from `CONTRACT_*` variables; pytest options map onto the same
keys (see `checks/conftest.py`). `load_config` is pure apart from looking at
the filesystem for the Postgres binaries and the working directory, and reports
every problem at once in a single `ConfigError`.
"""

import re
import shlex
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

PG_TOOLS = ("initdb", "pg_ctl", "createdb")
"""The PostgreSQL binaries the throwaway cluster needs."""

SERVICE_NAME = re.compile(r"^[a-z][a-z0-9]*-service$")
"""Gluon service names: `<domain>-service`, lower case."""

DEFAULT_SERVICE = "user-service"
DEFAULT_READINESS_PATH = "/health/ready"
DEFAULT_READINESS_DEADLINE_S = 60.0

TRUE_WORDS = frozenset({"1", "true", "yes"})
FALSE_WORDS = frozenset({"", "0", "false", "no"})


class ConfigError(Exception):
    """The configuration can't be used; `problems` lists every reason."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = tuple(problems)
        super().__init__(
            "Invalid harness configuration:\n" + "\n".join(f"- {p}" for p in self.problems)
        )


@dataclass(frozen=True, slots=True)
class HarnessConfig:
    """Everything a run needs to know before it starts anything."""

    target_argv: tuple[str, ...]
    target_cwd: Path
    target_name: str
    service: str
    pg_bin: Path
    readiness_path: str
    readiness_deadline_s: float
    keep_artifacts: bool


def load_config(
    raw: Mapping[str, str],
    *,
    cwd: Path,
    which: Callable[[str], str | None] = shutil.which,
) -> HarnessConfig:
    """Builds a `HarnessConfig` from `CONTRACT_*` settings.

    Args:
        raw: the settings, usually the environment overlaid with pytest options.
        cwd: the default working directory for the target.
        which: looks an executable up on the `PATH` (injected for tests).

    Raises:
        ConfigError: listing every invalid or missing setting.
    """
    problems: list[str] = []

    argv = _target_argv(raw.get("CONTRACT_TARGET_CMD", ""), problems)
    target_cwd = _target_cwd(raw.get("CONTRACT_TARGET_CWD"), cwd, problems)
    service = raw.get("CONTRACT_SERVICE") or DEFAULT_SERVICE
    if not SERVICE_NAME.match(service):
        problems.append(
            f"CONTRACT_SERVICE must look like '<domain>-service' in lower case, got {service!r}"
        )
    pg_bin = _pg_bin(raw.get("CONTRACT_PG_BIN"), which, problems)
    readiness_path = raw.get("CONTRACT_READINESS_PATH") or DEFAULT_READINESS_PATH
    if not readiness_path.startswith("/"):
        problems.append(f"CONTRACT_READINESS_PATH must start with '/', got {readiness_path!r}")
    deadline = _positive_float(
        "CONTRACT_READINESS_DEADLINE",
        raw.get("CONTRACT_READINESS_DEADLINE"),
        DEFAULT_READINESS_DEADLINE_S,
        problems,
    )
    keep = _flag("CONTRACT_KEEP_ARTIFACTS", raw.get("CONTRACT_KEEP_ARTIFACTS", ""), problems)

    if problems or argv is None or pg_bin is None:
        raise ConfigError(problems)
    return HarnessConfig(
        target_argv=argv,
        target_cwd=target_cwd,
        target_name=raw.get("CONTRACT_TARGET_NAME") or Path(argv[0]).name,
        service=service,
        pg_bin=pg_bin,
        readiness_path=readiness_path,
        readiness_deadline_s=deadline,
        keep_artifacts=keep,
    )


def find_pg_bin(
    explicit: str | None = None, *, which: Callable[[str], str | None] = shutil.which
) -> Path:
    """The PostgreSQL binary directory, resolved exactly as `load_config` does.

    Args:
        explicit: a `CONTRACT_PG_BIN` value, if set.
        which: looks an executable up on the `PATH` (injected for tests).

    Raises:
        ConfigError: if no directory with every binary in `PG_TOOLS` is found.
    """
    problems: list[str] = []
    directory = _pg_bin(explicit, which, problems)
    if directory is None:
        raise ConfigError(problems)
    return directory


def _target_argv(command: str, problems: list[str]) -> tuple[str, ...] | None:
    try:
        argv = tuple(shlex.split(command))
    except ValueError as error:
        problems.append(f"CONTRACT_TARGET_CMD can't be split like a shell command: {error}")
        return None
    if not argv:
        problems.append(
            "CONTRACT_TARGET_CMD is required: the command that starts the build under test"
        )
        return None
    return argv


def _target_cwd(value: str | None, default: Path, problems: list[str]) -> Path:
    if not value:
        return default
    path = Path(value)
    if not path.is_dir():
        problems.append(f"CONTRACT_TARGET_CWD is not a directory: {value}")
    return path


def _pg_bin(
    explicit: str | None, which: Callable[[str], str | None], problems: list[str]
) -> Path | None:
    if explicit:
        directory = Path(explicit)
        source = "CONTRACT_PG_BIN"
    else:
        found = which("pg_ctl")
        if found is None:
            problems.append(
                "PostgreSQL binaries not found: set CONTRACT_PG_BIN, or put pg_ctl on the PATH"
            )
            return None
        directory = Path(found).resolve().parent
        source = f"the directory of pg_ctl on the PATH ({directory})"
    missing = [tool for tool in PG_TOOLS if not (directory / tool).is_file()]
    if missing:
        problems.append(
            f"CONTRACT_PG_BIN: {source} lacks {', '.join(missing)} (needs {', '.join(PG_TOOLS)})"
        )
        return None
    return directory


def _positive_float(name: str, value: str | None, default: float, problems: list[str]) -> float:
    if not value:
        return default
    try:
        number = float(value)
    except ValueError:
        problems.append(f"{name} must be a number of seconds, got {value!r}")
        return default
    if number <= 0:
        problems.append(f"{name} must be positive, got {value!r}")
        return default
    return number


def _flag(name: str, value: str, problems: list[str]) -> bool:
    word = value.strip().lower()
    if word in TRUE_WORDS:
        return True
    if word not in FALSE_WORDS:
        problems.append(f"{name} must be one of 1/0, yes/no, true/false, got {value!r}")
    return False
