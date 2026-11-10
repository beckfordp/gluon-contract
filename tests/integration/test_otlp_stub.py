# SPDX-License-Identifier: MIT

"""The OTLP/HTTP stub the service under test exports spans to (RUST-1.2 spec FR4).

OTEL_EXPORTER_OTLP_ENDPOINT points at the stub; exporters append `/v1/traces`.
"""

import gzip
import json
import socket
import threading
import time
import urllib.error
import urllib.request

import pytest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue
from opentelemetry.proto.trace.v1.trace_pb2 import Span as ProtoSpan

from gluon_contract.otlp import Span
from gluon_contract.otlp_stub import OtlpStub, OtlpStubTimeoutError

TRACE = "0af7651916cd43dd8448eb211c80319c"


def export(*names: str) -> bytes:
    """A protobuf export from user-service with one server span per name."""
    request = ExportTraceServiceRequest()
    resource_spans = request.resource_spans.add()
    resource_spans.resource.attributes.append(
        KeyValue(key="service.name", value=AnyValue(string_value="user-service"))
    )
    scope = resource_spans.scope_spans.add()
    for index, name in enumerate(names, start=1):
        scope.spans.append(
            ProtoSpan(
                trace_id=bytes.fromhex(TRACE),
                span_id=index.to_bytes(8, "big"),
                name=name,
                kind=ProtoSpan.SPAN_KIND_SERVER,
            )
        )
    return request.SerializeToString()


def post(
    url: str, body: bytes, content_type: str, *, encoding: str | None = None
) -> tuple[int, str, bytes]:
    """POSTs and returns status, Content-Type and body, for any status."""
    headers = {"Content-Type": content_type}
    if encoding:
        headers["Content-Encoding"] = encoding
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.headers["Content-Type"], response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.headers["Content-Type"], error.read()


def test_a_protobuf_export_is_accepted_and_captured() -> None:
    """200 with an empty protobuf ExportTraceServiceResponse; the span is kept."""
    with OtlpStub() as stub:
        status, content_type, body = post(
            stub.traces_url, export("POST /auth/signup"), "application/x-protobuf"
        )
        assert status == 200
        assert content_type == "application/x-protobuf"
        assert ExportTraceServiceResponse.FromString(body) == ExportTraceServiceResponse()
        assert [span.name for span in stub.spans()] == ["POST /auth/signup"]
        assert stub.spans()[0].service_name == "user-service"


def test_an_otlp_json_export_is_accepted() -> None:
    """200 with `{}` for OTLP/JSON."""
    document = {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {"spans": [{"traceId": TRACE, "spanId": "00f067aa0ba902b7", "name": "json"}]}
                ]
            }
        ]
    }
    with OtlpStub() as stub:
        status, content_type, body = post(
            stub.traces_url, json.dumps(document).encode(), "application/json"
        )
        assert (status, content_type, json.loads(body)) == (200, "application/json", {})
        assert [span.name for span in stub.spans()] == ["json"]


def test_a_gzip_export_is_accepted() -> None:
    """Content-Encoding: gzip is decompressed."""
    with OtlpStub() as stub:
        status, _, _ = post(
            stub.traces_url,
            gzip.compress(export("zipped")),
            "application/x-protobuf",
            encoding="gzip",
        )
        assert status == 200
        assert [span.name for span in stub.spans()] == ["zipped"]


@pytest.mark.parametrize(
    ("body", "content_type", "status", "reason"),
    [
        (b"\xff\xff\xff", "application/x-protobuf", 400, "not a valid OTLP protobuf"),
        (b"{}", "text/plain", 415, "unsupported content type"),
    ],
)
def test_bad_exports_are_refused_and_recorded(
    body: bytes, content_type: str, status: int, reason: str
) -> None:
    """A malformed export gets 400, an unknown media type 415; both are kept for diagnosis."""
    with OtlpStub() as stub:
        assert post(stub.traces_url, body, content_type)[0] == status
        assert stub.spans() == []
        assert len(stub.rejected()) == 1
        assert reason in stub.rejected()[0]


def test_anything_but_posting_traces_is_404() -> None:
    """Other paths (metrics, logs) and other methods are not found."""
    with OtlpStub() as stub:
        assert post(f"{stub.endpoint}/v1/metrics", b"", "application/x-protobuf")[0] == 404
        with pytest.raises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(stub.traces_url, timeout=5)
        assert raised.value.code == 404


def test_wait_for_spans_returns_as_soon_as_they_arrive() -> None:
    """The wait ends on arrival, not after a fixed time."""
    with OtlpStub() as stub:
        sender = threading.Timer(
            0.3,
            post,
            args=(stub.traces_url, export("early", "outbox.write"), "application/x-protobuf"),
        )
        sender.start()
        started = time.monotonic()
        found = stub.wait_for_spans(lambda span: span.name == "outbox.write", timeout_s=10)
        assert time.monotonic() - started < 5
        assert [span.name for span in found] == ["outbox.write"]
        assert all(isinstance(span, Span) for span in stub.spans())
        sender.join()


def test_wait_for_spans_fails_at_its_deadline_saying_what_arrived() -> None:
    """A deadline miss lists the spans that did arrive."""
    with OtlpStub() as stub:
        post(stub.traces_url, export("POST /auth/login"), "application/x-protobuf")
        with pytest.raises(OtlpStubTimeoutError, match=r"POST /auth/login") as raised:
            stub.wait_for_spans(lambda span: span.name == "outbox.write", count=1, timeout_s=0.5)
        assert "0 of 1" in str(raised.value)


def test_the_port_is_closed_after_the_context() -> None:
    """Nothing listens once the stub has stopped."""
    with OtlpStub() as stub:
        port = stub.port
    with (
        pytest.raises(ConnectionRefusedError),
        socket.create_connection(("127.0.0.1", port), timeout=1),
    ):
        pass
