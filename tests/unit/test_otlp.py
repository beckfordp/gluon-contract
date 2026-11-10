# SPDX-License-Identifier: MIT

"""Decoding OTLP trace exports into typed spans (RUST-1.2 spec FR4).

The wire formats are OTLP/HTTP's: protobuf (`application/x-protobuf`, what
the Java and Rust exporters send by default) and OTLP/JSON (`application/json`),
whose ids are hex strings and whose enums are integers, unlike plain proto3 JSON.
"""

import gzip
import json
import zlib

import pytest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, ArrayValue, KeyValue
from opentelemetry.proto.trace.v1.trace_pb2 import Span as ProtoSpan
from opentelemetry.proto.trace.v1.trace_pb2 import Status

from gluon_contract.otlp import OtlpDecodeError, Span, decode_traces

TRACE = "0af7651916cd43dd8448eb211c80319c"
SERVER_SPAN = "b7ad6b7169203331"
OUTBOX_SPAN = "00f067aa0ba902b7"

EXPECTED = [
    Span(
        trace_id=TRACE,
        span_id=SERVER_SPAN,
        parent_span_id=None,
        name="POST /auth/signup",
        kind="SERVER",
        service_name="user-service",
        attributes={
            "http.request.method": "POST",
            "http.response.status_code": 201,
        },
        status="UNSET",
    ),
    Span(
        trace_id=TRACE,
        span_id=OUTBOX_SPAN,
        parent_span_id=SERVER_SPAN,
        name="outbox.write",
        kind="INTERNAL",
        service_name="user-service",
        attributes={
            "outbox.event_type": "UserRegistered",
            "retry": False,
            "ratio": 0.5,
            "tags": ("a", "b"),
        },
        status="ERROR",
    ),
]


def string(value: str) -> AnyValue:
    """An OTLP string value."""
    return AnyValue(string_value=value)


def protobuf_request() -> ExportTraceServiceRequest:
    """The EXPECTED spans as an exporter would send them."""
    request = ExportTraceServiceRequest()
    resource_spans = request.resource_spans.add()
    resource_spans.resource.attributes.append(
        KeyValue(key="service.name", value=string("user-service"))
    )
    scope = resource_spans.scope_spans.add()
    scope.spans.append(
        ProtoSpan(
            trace_id=bytes.fromhex(TRACE),
            span_id=bytes.fromhex(SERVER_SPAN),
            name="POST /auth/signup",
            kind=ProtoSpan.SPAN_KIND_SERVER,
            attributes=[
                KeyValue(key="http.request.method", value=string("POST")),
                KeyValue(key="http.response.status_code", value=AnyValue(int_value=201)),
            ],
        )
    )
    scope.spans.append(
        ProtoSpan(
            trace_id=bytes.fromhex(TRACE),
            span_id=bytes.fromhex(OUTBOX_SPAN),
            parent_span_id=bytes.fromhex(SERVER_SPAN),
            name="outbox.write",
            kind=ProtoSpan.SPAN_KIND_INTERNAL,
            attributes=[
                KeyValue(key="outbox.event_type", value=string("UserRegistered")),
                KeyValue(key="retry", value=AnyValue(bool_value=False)),
                KeyValue(key="ratio", value=AnyValue(double_value=0.5)),
                KeyValue(
                    key="tags",
                    value=AnyValue(array_value=ArrayValue(values=[string("a"), string("b")])),
                ),
            ],
            status=Status(code=Status.STATUS_CODE_ERROR),
        )
    )
    return request


OTLP_JSON = {
    "resourceSpans": [
        {
            "resource": {
                "attributes": [{"key": "service.name", "value": {"stringValue": "user-service"}}]
            },
            "scopeSpans": [
                {
                    "spans": [
                        {
                            "traceId": TRACE,
                            "spanId": SERVER_SPAN,
                            "name": "POST /auth/signup",
                            "kind": 2,
                            "attributes": [
                                {"key": "http.request.method", "value": {"stringValue": "POST"}},
                                {"key": "http.response.status_code", "value": {"intValue": "201"}},
                            ],
                        },
                        {
                            "traceId": TRACE,
                            "spanId": OUTBOX_SPAN,
                            "parentSpanId": SERVER_SPAN,
                            "name": "outbox.write",
                            "kind": 1,
                            "attributes": [
                                {
                                    "key": "outbox.event_type",
                                    "value": {"stringValue": "UserRegistered"},
                                },
                                {"key": "retry", "value": {"boolValue": False}},
                                {"key": "ratio", "value": {"doubleValue": 0.5}},
                                {
                                    "key": "tags",
                                    "value": {
                                        "arrayValue": {
                                            "values": [{"stringValue": "a"}, {"stringValue": "b"}]
                                        }
                                    },
                                },
                            ],
                            "status": {"code": 2},
                        },
                    ]
                }
            ],
        }
    ]
}


def test_protobuf_exports_decode_to_typed_spans() -> None:
    """application/x-protobuf: ids become lower-case hex, enums their names."""
    body = protobuf_request().SerializeToString()
    assert decode_traces(body, "application/x-protobuf") == EXPECTED


def test_otlp_json_exports_decode_to_the_same_spans() -> None:
    """application/json per OTLP/JSON: hex ids, integer enums, int64 as strings."""
    body = json.dumps(OTLP_JSON).encode()
    assert decode_traces(body, "application/json; charset=utf-8") == EXPECTED


def test_gzip_encoded_exports_decode() -> None:
    """Exporters may compress (OTEL_EXPORTER_OTLP_COMPRESSION=gzip)."""
    body = gzip.compress(protobuf_request().SerializeToString())
    assert decode_traces(body, "application/x-protobuf", content_encoding="gzip") == EXPECTED


def test_an_empty_export_has_no_spans() -> None:
    """An export with no resource spans decodes to nothing, not an error."""
    assert decode_traces(b"", "application/x-protobuf") == []


@pytest.mark.parametrize(
    ("body", "content_type", "message"),
    [
        (b"\xff\xff\xff", "application/x-protobuf", "not a valid OTLP protobuf"),
        (b"{not json", "application/json", "not valid OTLP/JSON"),
        (b"{}", "text/plain", "unsupported content type"),
    ],
)
def test_undecodable_exports_are_reported(body: bytes, content_type: str, message: str) -> None:
    """A bad export is an OtlpDecodeError saying why, never a raw parser exception."""
    with pytest.raises(OtlpDecodeError, match=message):
        decode_traces(body, content_type)


def one_span_with(*attributes: KeyValue) -> bytes:
    """A protobuf export holding one span with the given attributes."""
    request = ExportTraceServiceRequest()
    span = request.resource_spans.add().scope_spans.add().spans.add()
    span.trace_id = bytes.fromhex(TRACE)
    span.span_id = bytes.fromhex(SERVER_SPAN)
    span.attributes.extend(attributes)
    return request.SerializeToString()


def test_bytes_maps_and_empty_values_decode() -> None:
    """bytes stay bytes, kvlists become mappings, and a value-less attribute is None."""
    kvlist = AnyValue()
    kvlist.kvlist_value.values.append(KeyValue(key="inner", value=string("x")))
    body = one_span_with(
        KeyValue(key="raw", value=AnyValue(bytes_value=b"\x01\x02")),
        KeyValue(key="map", value=kvlist),
        KeyValue(key="empty", value=AnyValue()),
    )
    (span,) = decode_traces(body, "application/x-protobuf")
    assert span.attributes == {"raw": b"\x01\x02", "map": {"inner": "x"}, "empty": None}
    assert span.service_name is None


def test_deflate_encoded_exports_decode() -> None:
    """Content-Encoding: deflate (zlib) is accepted too."""
    body = zlib.compress(protobuf_request().SerializeToString())
    assert decode_traces(body, "application/x-protobuf", content_encoding="deflate") == EXPECTED


@pytest.mark.parametrize(
    ("body", "encoding", "message"),
    [
        (b"not gzip", "gzip", "not valid gzip"),
        (b"not zlib", "deflate", "not valid deflate"),
        (b"", "br", "unsupported content encoding"),
    ],
)
def test_bad_or_unknown_encodings_are_reported(body: bytes, encoding: str, message: str) -> None:
    """A corrupt body or an encoding the stub can't undo is an OtlpDecodeError."""
    with pytest.raises(OtlpDecodeError, match=message):
        decode_traces(body, "application/x-protobuf", content_encoding=encoding)
