# SPDX-License-Identifier: MIT

"""A stand-in for the build under test (RUST-1.2 spec FR10): a test double.

It honours the env-var contract so the runner can be proven before any real
implementation exists in the sandbox. It is not a model of user-service.

Serves on `<DOMAIN>_SERVICE_PORT`: `/health` (200), `/health/ready` (200 once
Postgres accepts a TCP connection, else 503), `/__env` (the environment it was
started with, as JSON). Serves `/metrics` on `<DOMAIN>_SERVICE_METRICS_PORT`.
Prints one JSON log line and exports one span to
`$OTEL_EXPORTER_OTLP_ENDPOINT/v1/traces`.

Flags for the runner's failure paths:
  --service NAME        the service whose variables to read (default user-service)
  --exit CODE           print to stderr and exit with CODE straight away
  --never-ready         answer 503 on the readiness path forever
  --ignore-sigterm      ignore SIGTERM, so only SIGKILL stops it
  --spawn-child         start a long-running child in the same process group
"""

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import urllib.request
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue
from opentelemetry.proto.trace.v1.trace_pb2 import Span

CHILD_MARKER = "stand-in-child"


def started_with() -> dict[str, str]:
    """The environment exactly as the process was started with it.

    Not os.environ: Python adds LC_CTYPE itself when no locale is set (PEP 538).
    """
    raw = Path("/proc/self/environ").read_bytes()
    pairs = (entry.split(b"=", 1) for entry in raw.split(b"\0") if entry)
    return {key.decode(): value.decode() for key, value in pairs}


def postgres_accepts() -> bool:
    """Whether the database named by the contract accepts a TCP connection."""
    address = (os.environ["POSTGRES_HOST"], int(os.environ["POSTGRES_PORT"]))
    try:
        with socket.create_connection(address, timeout=1):
            return True
    except OSError:
        return False


def serve(
    port: int, routes: dict[str, tuple[int, str, bytes] | None], *, never_ready: bool = False
) -> ThreadingHTTPServer:
    """Serves fixed routes (None means 'compute readiness') on 127.0.0.1:port."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            route = routes.get(self.path, (404, "text/plain", b"not found"))
            if route is None:
                ready = not never_ready and postgres_accepts()
                route = (200, "text/plain", b"ready") if ready else (503, "text/plain", b"no db")
            status, content_type, body = route
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            """Quiet: only the one JSON line goes to stdout."""

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def export_one_span(service: str) -> None:
    """One span, protobuf, to the OTLP endpoint from the contract."""
    request = ExportTraceServiceRequest()
    resource_spans = request.resource_spans.add()
    resource_spans.resource.attributes.append(
        KeyValue(key="service.name", value=AnyValue(string_value=service))
    )
    resource_spans.scope_spans.add().spans.append(
        Span(
            trace_id=os.urandom(16),
            span_id=os.urandom(8),
            name="stand-in.start",
            kind=Span.SPAN_KIND_INTERNAL,
        )
    )
    endpoint = os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"].rstrip("/") + "/v1/traces"
    post = urllib.request.Request(
        endpoint,
        data=request.SerializeToString(),
        headers={"Content-Type": "application/x-protobuf"},
        method="POST",
    )
    with urllib.request.urlopen(post, timeout=5):
        pass


def main() -> None:
    """Runs the stand-in until it is signalled."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", default="user-service")
    parser.add_argument("--exit", type=int, dest="exit_code")
    parser.add_argument("--never-ready", action="store_true")
    parser.add_argument("--ignore-sigterm", action="store_true")
    parser.add_argument("--spawn-child", action="store_true")
    arguments = parser.parse_args()

    if arguments.exit_code is not None:
        print("stand-in: exiting as asked", file=sys.stderr, flush=True)
        sys.exit(arguments.exit_code)
    if arguments.ignore_sigterm:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    if arguments.spawn_child:
        subprocess.Popen(["bash", "-c", f"exec -a {CHILD_MARKER} sleep 300"])

    prefix = arguments.service.removesuffix("-service").upper().replace("-", "_") + "_SERVICE"
    environment = json.dumps(started_with(), sort_keys=True).encode()
    serve(
        int(os.environ[f"{prefix}_PORT"]),
        {
            "/health": (200, "text/plain", b"ok"),
            "/health/ready": None,
            "/__env": (200, "application/json", environment),
        },
        never_ready=arguments.never_ready,
    )
    serve(
        int(os.environ[f"{prefix}_METRICS_PORT"]),
        {"/metrics": (200, "text/plain; version=0.0.4", b"stand_in_up 1\n")},
    )
    export_one_span(arguments.service)
    line = {"@timestamp": datetime.now(UTC).isoformat(), "message": "stand-in started"}
    print(json.dumps(line), flush=True)
    threading.Event().wait()


if __name__ == "__main__":
    main()
