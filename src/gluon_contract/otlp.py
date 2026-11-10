# SPDX-License-Identifier: MIT

"""Decoding OTLP trace exports into typed spans (RUST-1.2 spec FR4).

Pure: bytes in, spans out. The OTLP/HTTP stub (`otlp_stub.py`) feeds it what
exporters POST to `/v1/traces`. Two encodings, per the OTLP specification:
- `application/x-protobuf`: an `ExportTraceServiceRequest` message;
- `application/json`: OTLP/JSON, which differs from proto3's JSON mapping in
  that trace and span ids are hex strings (not base64) and enums are integers.
"""

import base64
import gzip
import json
import zlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from google.protobuf import json_format
from google.protobuf.message import DecodeError
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue
from opentelemetry.proto.trace.v1.trace_pb2 import Span as ProtoSpan
from opentelemetry.proto.trace.v1.trace_pb2 import Status

type AttributeValue = (
    str
    | bool
    | int
    | float
    | bytes
    | tuple[AttributeValue, ...]
    | Mapping[str, AttributeValue]
    | None
)
"""An OTLP AnyValue in Python terms; None for an attribute sent without a value."""

ID_FIELDS = ("traceId", "spanId", "parentSpanId")


class OtlpDecodeError(Exception):
    """An export that can't be decoded; the message says why."""


@dataclass(frozen=True, slots=True)
class Span:
    """One exported span, reduced to what contract checks look at."""

    trace_id: str
    """32 lower-case hex digits."""
    span_id: str
    """16 lower-case hex digits."""
    parent_span_id: str | None
    """None for a root span (or one whose parent is in another process)."""
    name: str
    kind: str
    """SERVER, CLIENT, INTERNAL, PRODUCER, CONSUMER or UNSPECIFIED."""
    service_name: str | None
    """The exporting resource's `service.name`."""
    attributes: Mapping[str, AttributeValue]
    status: str
    """UNSET, OK or ERROR."""


def decode_traces(
    body: bytes, content_type: str, *, content_encoding: str | None = None
) -> list[Span]:
    """Decodes one OTLP/HTTP trace export.

    Args:
        body: the request body.
        content_type: the request's Content-Type (parameters such as charset ignored).
        content_encoding: the request's Content-Encoding; `gzip` and `deflate` supported.

    Raises:
        OtlpDecodeError: for an unsupported encoding or content type, or a bad body.
    """
    raw = _decompress(body, content_encoding)
    media_type = content_type.split(";", 1)[0].strip().lower()
    if media_type == "application/x-protobuf":
        try:
            request = ExportTraceServiceRequest.FromString(raw)
        except DecodeError as error:
            raise OtlpDecodeError(f"not a valid OTLP protobuf export: {error}") from error
    elif media_type == "application/json":
        request = _from_otlp_json(raw)
    else:
        raise OtlpDecodeError(f"unsupported content type {content_type!r}")
    return _spans(request)


def _decompress(body: bytes, content_encoding: str | None) -> bytes:
    encoding = (content_encoding or "").strip().lower()
    try:
        if encoding == "gzip":
            return gzip.decompress(body)
        if encoding == "deflate":
            return zlib.decompress(body)
    except (OSError, zlib.error, EOFError) as error:
        raise OtlpDecodeError(f"body is not valid {encoding}: {error}") from error
    if encoding not in ("", "identity"):
        raise OtlpDecodeError(f"unsupported content encoding {content_encoding!r}")
    return body


def _from_otlp_json(raw: bytes) -> ExportTraceServiceRequest:
    try:
        document = json.loads(raw)
        for resource_spans in document.get("resourceSpans", []):
            for scope_spans in resource_spans.get("scopeSpans", []):
                for span in scope_spans.get("spans", []):
                    _hex_ids_to_base64(span)
        return json_format.ParseDict(
            document, ExportTraceServiceRequest(), ignore_unknown_fields=True
        )
    except (ValueError, AttributeError, TypeError, json_format.ParseError) as error:
        raise OtlpDecodeError(f"not valid OTLP/JSON: {error}") from error


def _hex_ids_to_base64(span: dict[str, Any]) -> None:
    """OTLP/JSON ids are hex; proto3's JSON mapping (ParseDict) expects base64."""
    for field in ID_FIELDS:
        if span.get(field):
            span[field] = base64.b64encode(bytes.fromhex(span[field])).decode("ascii")


def _spans(request: ExportTraceServiceRequest) -> list[Span]:
    spans = []
    for resource_spans in request.resource_spans:
        resource = _attributes(resource_spans.resource.attributes)
        service = resource.get("service.name")
        service_name = service if isinstance(service, str) else None
        for scope_spans in resource_spans.scope_spans:
            for span in scope_spans.spans:
                spans.append(
                    Span(
                        trace_id=span.trace_id.hex(),
                        span_id=span.span_id.hex(),
                        parent_span_id=span.parent_span_id.hex() or None,
                        name=span.name,
                        kind=ProtoSpan.SpanKind.Name(span.kind).removeprefix("SPAN_KIND_"),
                        service_name=service_name,
                        attributes=_attributes(span.attributes),
                        status=Status.StatusCode.Name(span.status.code).removeprefix(
                            "STATUS_CODE_"
                        ),
                    )
                )
    return spans


def _attributes(pairs: Any) -> dict[str, AttributeValue]:
    return {pair.key: _value(pair.value) for pair in pairs if isinstance(pair, KeyValue)}


def _value(value: AnyValue) -> AttributeValue:
    match value.WhichOneof("value"):
        case "string_value":
            return value.string_value
        case "bool_value":
            return value.bool_value
        case "int_value":
            return value.int_value
        case "double_value":
            return value.double_value
        case "bytes_value":
            return value.bytes_value
        case "array_value":
            return tuple(_value(item) for item in value.array_value.values)
        case "kvlist_value":
            return _attributes(value.kvlist_value.values)
        case _:
            return None
