# SPDX-License-Identifier: MIT

"""An OTLP/HTTP trace receiver for the service under test (RUST-1.2 spec FR4).

The service's `OTEL_EXPORTER_OTLP_ENDPOINT` points at `endpoint`; exporters
POST to `<endpoint>/v1/traces`. Every accepted span is kept for checks, and
`wait_for_spans` waits for them without fixed sleeps (exporters batch, so spans
arrive some time after the request that produced them).
"""

import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import TracebackType
from typing import Self

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceResponse

from gluon_contract.otlp import OtlpDecodeError, Span, decode_traces
from gluon_contract.ports import free_port

HOST = "127.0.0.1"
TRACES_PATH = "/v1/traces"


class OtlpStubTimeoutError(AssertionError):
    """The expected spans didn't arrive in time: a contract failure, not a harness error."""


class OtlpStub:
    """A local OTLP/HTTP endpoint that captures trace exports.

    Use as a context manager: entering starts the server on a background
    thread, leaving stops it and closes the port.
    """

    def __init__(self, *, port: int | None = None) -> None:
        """Prepares, but doesn't start, a receiver on `port` (a free one by default)."""
        self.port = port if port is not None else free_port()
        self.endpoint = f"http://{HOST}:{self.port}"
        self.traces_url = self.endpoint + TRACES_PATH
        self._spans: list[Span] = []
        self._rejected: list[str] = []
        self._arrived = threading.Condition()
        self._server = ThreadingHTTPServer((HOST, self.port), self._handler_class())
        self._server.daemon_threads = True
        self._thread = threading.Thread(
            target=self._server.serve_forever, name=f"otlp-stub-{self.port}", daemon=True
        )

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
        """Stops serving and closes the port."""
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def spans(self) -> list[Span]:
        """Every span accepted so far, in arrival order."""
        with self._arrived:
            return list(self._spans)

    def rejected(self) -> list[str]:
        """Why each refused export was refused, for diagnosing a bad exporter."""
        with self._arrived:
            return list(self._rejected)

    def wait_for_spans(
        self,
        predicate: Callable[[Span], bool] = lambda _span: True,
        *,
        count: int = 1,
        timeout_s: float = 10.0,
    ) -> list[Span]:
        """Waits until at least `count` accepted spans match `predicate`; returns them all.

        Raises:
            OtlpStubTimeoutError: if they haven't arrived within `timeout_s`, listing what did.
        """

        def matching() -> list[Span]:
            return [span for span in self._spans if predicate(span)]

        with self._arrived:
            if self._arrived.wait_for(lambda: len(matching()) >= count, timeout=timeout_s):
                return matching()
            received = ", ".join(f"{s.service_name}: {s.name}" for s in self._spans) or "none"
            raise OtlpStubTimeoutError(
                f"{len(matching())} of {count} expected span(s) after {timeout_s}s; "
                f"received: {received}"
                + (f"; rejected exports: {self._rejected}" if self._rejected else "")
            )

    def _accept(self, spans: list[Span]) -> None:
        with self._arrived:
            self._spans.extend(spans)
            self._arrived.notify_all()

    def _reject(self, reason: str) -> None:
        with self._arrived:
            self._rejected.append(reason)
            self._arrived.notify_all()

    def _handler_class(self) -> type[BaseHTTPRequestHandler]:
        stub = self

        class Handler(BaseHTTPRequestHandler):
            """POST /v1/traces; everything else is 404."""

            def do_POST(self) -> None:
                if self.path.split("?", 1)[0] != TRACES_PATH:
                    self._answer(404, "text/plain", b"not found")
                    return
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                content_type = self.headers.get("Content-Type", "")
                try:
                    spans = decode_traces(
                        body, content_type, content_encoding=self.headers.get("Content-Encoding")
                    )
                except OtlpDecodeError as error:
                    stub._reject(str(error))
                    status = 415 if "content type" in str(error) else 400
                    self._answer(status, "text/plain", str(error).encode())
                    return
                stub._accept(spans)
                if content_type.lower().startswith("application/json"):
                    self._answer(200, "application/json", b"{}")
                else:
                    self._answer(
                        200,
                        "application/x-protobuf",
                        ExportTraceServiceResponse().SerializeToString(),
                    )

            def do_GET(self) -> None:
                self._answer(404, "text/plain", b"not found")

            def _answer(self, status: int, content_type: str, body: bytes) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                """Quiet: the harness reports outcomes, not access logs."""

        return Handler
