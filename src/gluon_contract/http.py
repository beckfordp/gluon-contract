# SPDX-License-Identifier: MIT

"""Raw HTTP for contract checks (RUST-1.3).

The standard library's `http.client`, so a check controls exactly what is sent
(method, headers including none at all, raw body) and sees exactly what came
back. Captured exchanges (`capture.py`) parse into the same `HttpResponse`, so
checks compare like with like.
"""

import http.client
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """A response: status, headers in arrival order, body bytes."""

    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes

    def header(self, name: str) -> str | None:
        """The first value of header `name` (case-insensitive), or None."""
        wanted = name.lower()
        return next((value for key, value in self.headers if key.lower() == wanted), None)

    def header_set(self, name: str) -> set[str]:
        """Every comma-separated item of every `name` header, as a set."""
        wanted = name.lower()
        return {
            item.strip()
            for key, value in self.headers
            if key.lower() == wanted
            for item in value.split(",")
            if item.strip()
        }

    @property
    def text(self) -> str:
        """The body as UTF-8 text."""
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        """The body as JSON.

        Raises:
            ValueError: quoting the body when it isn't JSON.
        """
        try:
            return json.loads(self.body)
        except ValueError as error:
            raise ValueError(f"body is not JSON: {self.text[:200]!r}") from error


def json_body(value: Any) -> bytes:
    """A compact UTF-8 JSON request body (non-ASCII unescaped, as a browser sends it)."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def request(
    base_url: str,
    method: str,
    path: str,
    *,
    body: bytes | None = None,
    headers: Mapping[str, str] | None = None,
    timeout_s: float = 30.0,
) -> HttpResponse:
    """Sends one request with exactly the given headers (plus Host and Content-Length)."""
    parts = urlsplit(base_url)
    connection = http.client.HTTPConnection(
        parts.hostname or "127.0.0.1", parts.port, timeout=timeout_s
    )
    try:
        connection.request(method, path, body=body, headers=dict(headers or {}))
        raw = connection.getresponse()
        return HttpResponse(status=raw.status, headers=tuple(raw.getheaders()), body=raw.read())
    finally:
        connection.close()
