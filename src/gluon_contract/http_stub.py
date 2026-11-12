# SPDX-License-Identifier: MIT

"""A scriptable stand-in for user-service's `GET /users/{id}` (RUST-6.1).

The consumer probe's resilience-wrapped lookup (ADR 0025's recipient lookup,
ADR 0028 decision 8) calls this. By default it answers as user-service does
(200, `{userId, email, createdAt}`), and any other path isn't found (404,
empty); a check scripts the next answers to be a status, a delay or a reset
connection, and reads back every request it got. The harness also starts one
per service a service calls (RPN-3); until a check scripts it, a stub standing
in for order-service finds no order.
"""

import json
import re
import socket
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import TracebackType
from typing import Self

HOST = "127.0.0.1"
USER_PATH = re.compile(r"^/users/([^/?]+)$")


@dataclass(frozen=True, slots=True)
class Status:
    """Answer with this status (the default body for 200 on a user path, else empty)."""

    code: int


@dataclass(frozen=True, slots=True)
class Delay:
    """Wait `seconds`, then answer as `then` says (the default answer if None)."""

    seconds: float
    then: "Status | None" = None


@dataclass(frozen=True, slots=True)
class Reset:
    """Close the connection without answering."""


type Behaviour = Status | Delay | Reset


@dataclass(frozen=True, slots=True)
class StubRequest:
    """One request received: method, path, headers (names lower-case)."""

    method: str
    path: str
    headers: dict[str, str] = field(default_factory=dict)


def user_body(user_id: str) -> bytes:
    """What user-service answers for an existing user (capture http/users-200.txt's shape)."""
    return json.dumps(
        {
            "userId": user_id,
            "email": f"{user_id}@example.com",
            "createdAt": "2026-11-09T18:43:19.511602Z",
        },
        separators=(",", ":"),
    ).encode()


class HttpStub:
    """The stub server; a context manager."""

    def __init__(self) -> None:
        self._script: deque[Behaviour] = deque()
        self._requests: list[StubRequest] = []
        self._lock = threading.Lock()
        self._server = ThreadingHTTPServer((HOST, 0), self._handler())
        self._server.daemon_threads = True
        self.port: int = self._server.server_address[1]
        self.url = f"http://{HOST}:{self.port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> Self:
        """Starts serving."""
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Stops serving and frees the port."""
        self._server.shutdown()
        self._server.server_close()

    def script(self, *behaviours: Behaviour) -> None:
        """Queues the next answers, replacing any still queued."""
        with self._lock:
            self._script = deque(behaviours)

    def requests(self) -> list[StubRequest]:
        """Every request so far, in arrival order."""
        with self._lock:
            return list(self._requests)

    def wait_for_requests(self, count: int, *, timeout_s: float = 20.0) -> list[StubRequest]:
        """Waits until `count` requests have arrived.

        Raises:
            AssertionError: how many came, if fewer within `timeout_s`.
        """
        deadline = time.monotonic() + timeout_s
        while True:
            got = self.requests()
            if len(got) >= count:
                return got
            if time.monotonic() >= deadline:
                raise AssertionError(f"{len(got)} of {count} requests after {timeout_s}s: {got}")
            time.sleep(0.05)

    def _next(self) -> Behaviour | None:
        with self._lock:
            return self._script.popleft() if self._script else None

    def _record(self, request: StubRequest) -> None:
        with self._lock:
            self._requests.append(request)

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        stub = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self) -> None:
                stub._record(
                    StubRequest("GET", self.path, {k.lower(): v for k, v in self.headers.items()})
                )
                behaviour = stub._next()
                if isinstance(behaviour, Delay):
                    time.sleep(behaviour.seconds)
                    behaviour = behaviour.then
                if isinstance(behaviour, Reset):
                    self.close_connection = True
                    self.connection.shutdown(socket.SHUT_RDWR)
                    return
                match = USER_PATH.match(self.path)
                default = 200 if match else 404
                status = default if behaviour is None else behaviour.code
                body = user_body(match.group(1)) if status == 200 and match else b""
                self.send_response(status)
                if body:
                    self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                """Quiet: the harness reports, not the server."""

        return Handler
