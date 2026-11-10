# SPDX-License-Identifier: MIT

"""Captured exchanges from the Scala service (RUST-1.3).

`contracts/<service>/<capture>/http/*.txt` are `curl -si` outputs: a status
line, headers, a blank line, the body. They parse into `HttpResponse`, the
same type live responses have.
"""

import re
from pathlib import Path

from gluon_contract.contracts import CONTRACTS_ROOT, latest_capture
from gluon_contract.http import HttpResponse

STATUS_LINE = re.compile(rb"^HTTP/\d(?:\.\d)? (\d{3})")


class CaptureError(Exception):
    """A capture file that can't be read as an HTTP exchange."""


def parse_exchange(raw: bytes) -> HttpResponse:
    """Parses one `curl -si` output.

    Raises:
        CaptureError: when it doesn't start with an HTTP status line.
    """
    head, _, body = raw.replace(b"\r\n", b"\n").partition(b"\n\n")
    lines = head.split(b"\n")
    status = STATUS_LINE.match(lines[0])
    if status is None:
        raise CaptureError(f"not an HTTP response: {raw[:60]!r}")
    headers = tuple(
        (name.strip().decode("latin-1"), value.strip().decode("latin-1"))
        for name, _, value in (line.partition(b":") for line in lines[1:] if b":" in line)
    )
    return HttpResponse(status=int(status.group(1)), headers=headers, body=body)


def capture_file(name: str, *, service: str = "user-service", root: Path = CONTRACTS_ROOT) -> Path:
    """A file from the service's latest capture, e.g. `metrics.txt`.

    Raises:
        FileNotFoundError: when the capture has no such file.
    """
    path = latest_capture(root, service) / name
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def load_exchange(
    name: str, *, service: str = "user-service", root: Path = CONTRACTS_ROOT
) -> HttpResponse:
    """The captured exchange `http/<name>.txt` from the service's latest capture."""
    path = latest_capture(root, service) / "http" / f"{name}.txt"
    return parse_exchange(path.read_bytes())
