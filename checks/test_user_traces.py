# SPDX-License-Identifier: MIT

"""Traces (gluon PLAN.md RUST-1.7; ADR 0028 "Traces" row; ADR 0021).

Reference: capture stdout.log (the Scala service's spans as its console
exporter printed them: names, kinds, attributes), db-outbox-events.jsonl and
http/traceparent-signup.txt, purerest ServerTracing's contract (one SERVER
span per request, continuing an inbound W3C traceparent, else a new root).
"""

import time
from typing import Any

import psycopg
import pytest
from support import new_email, new_traceparent, signed_up

from gluon_contract.formats import parse_traceparent
from gluon_contract.harness import Harness
from gluon_contract.http import request
from gluon_contract.otlp import Span

pytestmark = pytest.mark.service("user-service")
"""user-service's contract: deselected in a run for another service (RPN-3)."""

type Db = psycopg.Connection[tuple[Any, ...]]


def traced_signup(harness: Harness) -> tuple[str, str, str, Span, Span]:
    """A signup with a fresh traceparent: (trace, parent span, userId, server, outbox span)."""
    inbound = new_traceparent()
    parts = parse_traceparent(inbound)
    assert parts is not None
    user_id = signed_up(harness, new_email(), traceparent=inbound)["userId"]
    spans = harness.otlp.wait_for_spans(
        lambda s: s.trace_id == parts.trace_id and s.name in ("POST /auth/signup", "outbox.write"),
        count=2,
        timeout_s=20,
    )
    server = next(s for s in spans if s.name == "POST /auth/signup")
    outbox = next(s for s in spans if s.name == "outbox.write")
    return parts.trace_id, parts.span_id, user_id, server, outbox


def test_spans_carry_the_service_name(harness: Harness) -> None:
    """service.name is user-service.

    Source: capture stdout.log ("[tracer: user-service:]"); ADR 0028 Traces row.
    """
    _, _, _, server, outbox = traced_signup(harness)
    assert server.service_name == outbox.service_name == "user-service"


def test_a_request_span_continues_an_inbound_traceparent(harness: Harness) -> None:
    """A SERVER span named "POST /auth/signup", child of the caller's span, with HTTP attributes.

    Source: capture stdout.log ('POST /auth/signup' SERVER, http.request.method,
    url.path, http.response.status_code); purerest ServerTracing (joins an inbound
    W3C context).
    """
    trace, parent, _, server, _ = traced_signup(harness)
    assert (server.kind, server.trace_id, server.parent_span_id) == ("SERVER", trace, parent)
    assert server.attributes == {
        "http.request.method": "POST",
        "url.path": "/auth/signup",
        "http.response.status_code": 201,
    }


def test_the_outbox_write_is_an_internal_span_under_the_request(harness: Harness) -> None:
    """outbox.write: INTERNAL, a child of the request span, naming the event and aggregate.

    Source: capture stdout.log ('outbox.write' INTERNAL, outbox.aggregate_id,
    outbox.event_type); ADR 0008 amendment 2026-11-05.
    """
    trace, _, user_id, server, outbox = traced_signup(harness)
    assert (outbox.kind, outbox.trace_id, outbox.parent_span_id) == (
        "INTERNAL",
        trace,
        server.span_id,
    )
    assert outbox.attributes == {
        "outbox.event_type": "UserRegistered",
        "outbox.aggregate_id": user_id,
    }


def test_the_outbox_row_names_the_outbox_write_span(harness: Harness, db: Db) -> None:
    """trace_parent is that span's context, sampled, so consumers join the trace.

    Source: capture db-outbox-events.jsonl (trace_parent = the outbox.write span);
    ADR 0008 amendment 2026-11-05. The random-trace flag (capture: 03) is not
    contract; the sampled bit is.
    """
    trace, _, user_id, _, outbox = traced_signup(harness)
    row = db.execute(
        "select trace_parent from outbox_events where aggregate_id = %s", (user_id,)
    ).fetchone()
    assert row is not None
    parts = parse_traceparent(row[0] or "")
    assert parts is not None, row
    assert (parts.trace_id, parts.span_id, parts.sampled) == (trace, outbox.span_id, True)


def test_a_request_without_traceparent_starts_a_new_trace(harness: Harness) -> None:
    """No inbound context: the request span is a root.

    Source: purerest ServerTracing ("otherwise it starts a new root trace").
    """
    user_id = signed_up(harness, new_email())["userId"]
    (outbox,) = harness.otlp.wait_for_spans(
        lambda s: s.name == "outbox.write" and s.attributes.get("outbox.aggregate_id") == user_id,
        timeout_s=20,
    )
    (server,) = harness.otlp.wait_for_spans(
        lambda s: s.trace_id == outbox.trace_id and s.name == "POST /auth/signup",
        timeout_s=20,
    )
    assert server.parent_span_id is None
    assert outbox.parent_span_id == server.span_id


def only_span_of(harness: Harness, inbound: str) -> Span:
    """The single span of the trace `inbound` started."""
    parts = parse_traceparent(inbound)
    assert parts is not None
    trace_id = parts.trace_id
    (span,) = harness.otlp.wait_for_spans(lambda s: s.trace_id == trace_id, timeout_s=20)
    return span


def test_an_unmatched_path_span_has_no_status_code(harness: Harness) -> None:
    """A path no route matches is traced, but without http.response.status_code.

    Source: capture stdout.log ('GET /no-such-path' SERVER with two attributes,
    totalAddedValues=2); purerest ServerTracing adds the status code only to a
    response the routes produced, and the 404 for an unmatched path comes from
    outside them. Implicit behaviour (RUST-1.9).
    """
    inbound = new_traceparent()
    parts = parse_traceparent(inbound)
    assert parts is not None
    response = request(harness.base_url, "GET", "/no-such-path", headers={"traceparent": inbound})
    assert response.status == 404
    (span,) = harness.otlp.wait_for_spans(lambda s: s.trace_id == parts.trace_id, timeout_s=20)
    assert (span.name, span.kind) == ("GET /no-such-path", "SERVER")
    assert span.attributes == {"http.request.method": "GET", "url.path": "/no-such-path"}


def test_a_cors_preflight_is_not_traced(harness: Harness) -> None:
    """The CORS middleware answers a preflight itself, outside server tracing: no span.

    Source: capture stdout.log (no OPTIONS span, though http/cors-preflight.txt was
    captured in the same run); user-service AppRoutes (CORS wraps the traced
    routes). Implicit behaviour (RUST-1.9).
    """
    inbound = new_traceparent()
    parts = parse_traceparent(inbound)
    assert parts is not None
    preflight = request(
        harness.base_url,
        "OPTIONS",
        "/auth/signup",
        headers={
            "Origin": "http://example.com",
            "Access-Control-Request-Method": "POST",
            "traceparent": inbound,
        },
    )
    assert preflight.status == 200
    # A later traced request's span arriving means the preflight's would have too.
    marker = new_traceparent()
    marker_parts = parse_traceparent(marker)
    assert marker_parts is not None
    request(harness.base_url, "GET", "/health", headers={"traceparent": marker})
    harness.otlp.wait_for_spans(lambda s: s.trace_id == marker_parts.trace_id, timeout_s=20)
    assert [s for s in harness.otlp.spans() if s.trace_id == parts.trace_id] == []


def test_only_a_server_error_marks_the_span_as_error(harness: Harness) -> None:
    """2xx and 4xx spans keep status UNSET; a 5xx (readiness with Postgres down) is ERROR.

    Source: purerest ServerTracing ("a 5xx marks it Error"); capture openapi.yaml
    (readiness 503 when Postgres doesn't answer). Stops and restarts the database.
    """
    ok, client_error, server_error = new_traceparent(), new_traceparent(), new_traceparent()
    request(harness.base_url, "GET", "/health", headers={"traceparent": ok})
    request(harness.base_url, "GET", "/users/not-a-uuid", headers={"traceparent": client_error})
    harness.postgres.stop()
    try:
        response = request(
            harness.base_url, "GET", "/health/ready", headers={"traceparent": server_error}
        )
        assert response.status == 503
    finally:
        harness.postgres.start()
    statuses = {
        name: only_span_of(harness, inbound).status
        for name, inbound in (("ok", ok), ("4xx", client_error), ("5xx", server_error))
    }
    assert statuses == {"ok": "UNSET", "4xx": "UNSET", "5xx": "ERROR"}
    deadline = time.monotonic() + 30
    while request(harness.base_url, "GET", "/health/ready").status != 200:
        assert time.monotonic() < deadline, "not ready again 30 s after Postgres came back"
        time.sleep(0.2)
