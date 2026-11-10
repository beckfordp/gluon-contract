# SPDX-License-Identifier: MIT

"""`contracts/`: Scala-generated artifacts and captures from the laptop (spec FR9).

The sandbox can't build the Scala service (ADR 0028), so what it generates, and
behaviour nothing documents, is produced on the laptop with the commands in
`contracts/<service>/CAPTURE.md` and committed as `contracts/<service>/<capture>/`.
Every capture directory carries a PROVENANCE.md; one without it can't be trusted.
"""

from pathlib import Path

CONTRACTS_ROOT = Path(__file__).resolve().parents[2] / "contracts"
"""This repo's `contracts/` directory."""

PROVENANCE = "PROVENANCE.md"


class ContractsError(Exception):
    """`contracts/` is missing a capture or a capture's provenance."""


def capture_dirs(root: Path, service: str) -> list[Path]:
    """The service's capture directories, oldest first (names are dated).

    Raises:
        ContractsError: naming every capture directory without a PROVENANCE.md.
    """
    service_dir = root / service
    if not service_dir.is_dir():
        return []
    captures = sorted(path for path in service_dir.iterdir() if path.is_dir())
    unproven = [path.name for path in captures if not (path / PROVENANCE).is_file()]
    if unproven:
        raise ContractsError(
            f"{service_dir}: capture(s) {', '.join(unproven)} lack {PROVENANCE}; "
            "record who ran which commands, where, and the user-service commit"
        )
    return captures


def latest_capture(root: Path, service: str) -> Path:
    """The newest capture for `service`.

    Raises:
        ContractsError: if there is none yet, pointing at the capture instructions.
    """
    captures = capture_dirs(root, service)
    if not captures:
        raise ContractsError(
            f"no capture for {service} yet: run the commands in "
            f"{root / service / 'CAPTURE.md'} on the laptop and commit the result "
            f"as {root / service}/<date>/ with a {PROVENANCE}"
        )
    return captures[-1]
