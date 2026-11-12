# SPDX-License-Identifier: MIT

"""The consumer probe (gluon PLAN.md RUST-6.5; ADR 0028 decision 8, "Consumer probe" row).

The probe stands in for notification-service's consumers, so it is judged as they
behave. Reference: ADR 0025 (the lookup; 400/404 unresolved, never retried; 5xx and
transport failures retried, then dead-lettered); docs/system-design.md "Envelope"
(unknown eventType skipped silently); purekafka KafkaTracing.traced, DeadLetter,
StreamSupervisor, EventAge, ConsumerLag; purerest Retry, CircuitBreaker,
ClientTracing, ClientMetrics; notification-service EnvelopeHandler, UserClient,
UserRegisteredConsumer ("<topic> process" spans) and application.conf (defaults).
"""

import json
import secrets
import time
import uuid
from collections.abc import Callable
from typing import Any

import pytest

from gluon_contract.cdc import KafkaBroker
from gluon_contract.http_stub import HttpStub, Reset, Status
from gluon_contract.metrics import metric_shapes, samples
from gluon_contract.pytest_plugin import ProbeRun

pytestmark = pytest.mark.service("user-service")
"""Run with user-service's checks, as since RUST-6.x: the probe is built in user-service-rs
and judged in its session. Deselected in a run for another service (RPN-3)."""

type Probe = Callable[..., ProbeRun]
EVENT_AGE_BUCKETS = (
    *(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0),
    float("inf"),
)
"""purekafka EventAge.boundaries, and the +Inf bucket every histogram has."""


def envelope(event_type: str, payload: dict[str, Any]) -> str:
    """An event in the shared envelope (docs/system-design.md "Envelope")."""
    user_id = payload.get("userId", str(uuid.uuid4()))
    return json.dumps(
        {
            "eventId": str(uuid.uuid4()),
            "eventType": event_type,
            "timestamp": "2026-11-09T18:43:19.487722Z",
            "source": "user-service",
            "correlationId": user_id,
            "payload": payload,
        }
    )


def registered(kafka: KafkaBroker, run: ProbeRun, *, traceparent: str | None = None) -> str:
    """Publishes a UserRegistered on the probe's topic; returns the userId."""
    user_id = str(uuid.uuid4())
    headers = {"correlation_id": user_id}
    if traceparent is not None:
        headers["traceparent"] = traceparent
    value = envelope("UserRegistered", {"userId": user_id, "email": f"{user_id}@example.com"})
    kafka.produce(run.topic, user_id, value, headers)
    return user_id


def lookups(stub: HttpStub, user_id: str) -> int:
    """How many lookups for `user_id` the stub got."""
    return sum(1 for r in stub.requests() if r.path == f"/users/{user_id}")


def wait_until(condition: Callable[[], bool], what: str, timeout_s: float = 30.0) -> None:
    """Polls until `condition` holds."""
    deadline = time.monotonic() + timeout_s
    while not condition():
        assert time.monotonic() < deadline, f"not within {timeout_s}s: {what}"
        time.sleep(0.2)


def dead_letter(kafka: KafkaBroker, run: ProbeRun, key: str) -> None:
    """Waits for `key`'s record on the probe's DLQ topic."""
    kafka.record(run.dlq_topic, lambda r: r.key == key, timeout_s=30)


def settle(seconds: float = 2.0) -> None:
    """Gives the probe time to do anything it shouldn't before a check looks."""
    time.sleep(seconds)


def test_a_lookup_is_made_per_event_inside_the_events_trace(
    kafka: KafkaBroker, lookup_stub: HttpStub, probe: Probe
) -> None:
    """One GET /users/{userId}; a CONSUMER span "<topic> process" joining the record's
    traceparent, a CLIENT span under it, and the lookup carrying that span's context.

    Source: ADR 0025 (GET /users/{id}); purekafka KafkaTracing.traced (CONSUMER,
    messaging.system, messaging.destination.name); notification-service
    UserRegisteredConsumer (span name "<topic> process"); purerest ClientTracing
    ("<METHOD> <host>", CLIENT, http.request.method, server.address, url.path,
    http.response.status_code; traceparent injected).
    """
    run = probe()
    trace, parent = secrets.token_hex(16), secrets.token_hex(8)
    user_id = registered(kafka, run, traceparent=f"00-{trace}-{parent}-01")
    (request,) = lookup_stub.wait_for_requests(1)
    assert request.path == f"/users/{user_id}"
    consumer, client = _consumer_and_client(run, trace)
    assert (consumer.kind, consumer.name, consumer.parent_span_id) == (
        "CONSUMER",
        f"{run.topic} process",
        parent,
    )
    assert consumer.attributes == {
        "messaging.system": "kafka",
        "messaging.destination.name": run.topic,
    }
    assert (client.kind, client.name, client.parent_span_id) == (
        "CLIENT",
        "GET 127.0.0.1",
        consumer.span_id,
    )
    assert client.attributes == {
        "http.request.method": "GET",
        "server.address": "127.0.0.1",
        "url.path": f"/users/{user_id}",
        "http.response.status_code": 200,
    }
    assert request.headers["traceparent"].split("-")[1:3] == [trace, client.span_id]


def _consumer_and_client(run: ProbeRun, trace: str) -> tuple[Any, Any]:
    spans = run.otlp.wait_for_spans(lambda s: s.trace_id == trace, count=2, timeout_s=20)
    consumer = next(s for s in spans if s.kind == "CONSUMER")
    client = next(s for s in spans if s.kind == "CLIENT")
    return consumer, client


def test_an_unknown_event_type_is_skipped(
    kafka: KafkaBroker, lookup_stub: HttpStub, probe: Probe
) -> None:
    """No lookup, no DLQ; the next event is handled and both offsets are committed.

    Source: docs/system-design.md "Envelope" (an unrecognised eventType is skipped,
    not an error); notification-service EnvelopeHandler ("event type with no route").
    """
    run = probe()
    kafka.produce(run.topic, "k", envelope("UserDeleted", {"userId": "x"}), {})
    user_id = registered(kafka, run)
    wait_until(lambda: lookups(lookup_stub, user_id) == 1, "the second event's lookup")
    settle()
    assert len(lookup_stub.requests()) == 1
    assert kafka.records(run.dlq_topic) == []
    wait_until(lambda: kafka.committed(run.group, run.topic) == {0: 2}, "both offsets committed")


def test_a_poison_message_is_dead_lettered_with_its_key_and_value(
    kafka: KafkaBroker, lookup_stub: HttpStub, probe: Probe
) -> None:
    """An undecodable envelope goes to <topic>-dlq unchanged, after the bounded retries;
    the stream carries on.

    Source: purekafka DeadLetter (publishes the message's own key and value to
    <topic>-dlq, then returns); notification-service EnvelopeHandler (undecodable →
    dead-lettered raw).
    """
    run = probe(PROBE_DLQ_BASE_DELAY="10ms")
    kafka.produce(run.topic, "poison-key", "{not an envelope", {})
    user_id = registered(kafka, run)
    dead = kafka.record(run.dlq_topic, lambda r: r.key == "poison-key", timeout_s=30)
    assert dead.value == "{not an envelope"
    wait_until(lambda: lookups(lookup_stub, user_id) == 1, "the next event handled")


def test_transient_failures_are_retried(
    kafka: KafkaBroker, lookup_stub: HttpStub, probe: Probe
) -> None:
    """A 503 and a reset connection, then 200: three lookups, nothing dead-lettered.

    Source: ADR 0025 (transport/5xx failures retried); purerest Retry (5xx retried);
    purekafka DeadLetter (processing retried when the lookup raises).
    """
    run = probe(PROBE_LOOKUP_BASE_DELAY="10ms", PROBE_DLQ_BASE_DELAY="10ms")
    lookup_stub.script(Status(503), Reset())
    user_id = registered(kafka, run)
    wait_until(lambda: lookups(lookup_stub, user_id) == 3, "three lookups")
    settle()
    assert lookups(lookup_stub, user_id) == 3
    assert kafka.records(run.dlq_topic) == []


def test_an_unknown_user_is_unresolved_not_retried(
    kafka: KafkaBroker, lookup_stub: HttpStub, probe: Probe
) -> None:
    """404 is terminal: one lookup, no retry, nothing dead-lettered.

    Source: ADR 0025 decision 4 (400/404 → unresolved, no retry); notification-service
    UserClient (400/404 → None).
    """
    run = probe()
    lookup_stub.script(Status(404))
    user_id = registered(kafka, run)
    wait_until(lambda: lookups(lookup_stub, user_id) == 1, "one lookup")
    settle()
    assert lookups(lookup_stub, user_id) == 1
    assert kafka.records(run.dlq_topic) == []


def test_persistent_failures_are_dead_lettered_after_both_retry_layers(
    kafka: KafkaBroker, lookup_stub: HttpStub, probe: Probe
) -> None:
    """Always 500, 1 HTTP retry and 1 processing retry: 4 lookups, then the DLQ.

    Source: purerest Retry (returns the last 5xx when exhausted); notification-service
    UserClient (an unexpected status raises); purekafka DeadLetter (retries
    processing, then publishes key and value to <topic>-dlq).
    """
    run = probe(
        PROBE_LOOKUP_MAX_RETRIES="1",
        PROBE_LOOKUP_BASE_DELAY="10ms",
        PROBE_DLQ_MAX_RETRIES="1",
        PROBE_DLQ_BASE_DELAY="10ms",
    )
    lookup_stub.script(*[Status(500)] * 8)
    user_id = registered(kafka, run)
    dead = kafka.record(run.dlq_topic, lambda r: r.key == user_id, timeout_s=30)
    assert json.loads(dead.value or "")["payload"]["userId"] == user_id
    assert lookups(lookup_stub, user_id) == 4


def test_the_circuit_breaker_opens_and_then_rejects_without_calling(
    kafka: KafkaBroker, lookup_stub: HttpStub, probe: Probe
) -> None:
    """Threshold 2: two failed lookups open it; the third event is rejected without a
    call. All three are dead-lettered; the breaker's metrics say so.

    Source: purerest CircuitBreaker (a COUNT_BASED window of failure-threshold calls,
    all failing, opens it; rejections counted; state gauge 1 for the current state;
    transitions counted); purekafka DeadLetter.
    """
    run = probe(
        PROBE_LOOKUP_MAX_RETRIES="0",
        PROBE_DLQ_MAX_RETRIES="0",
        PROBE_BREAKER_FAILURE_THRESHOLD="2",
        PROBE_BREAKER_RESET_TIMEOUT="60s",
    )
    lookup_stub.script(*[Status(500)] * 8)
    users = [registered(kafka, run) for _ in range(3)]
    for user_id in users:
        dead_letter(kafka, run, user_id)
    assert len(lookup_stub.requests()) == 2
    text = run.scrape()
    states = {
        labels["state"]: value for labels, value in samples(text, "purerest_circuit_breaker_state")
    }
    assert states == {"CLOSED": 0.0, "OPEN": 1.0, "HALF_OPEN": 0.0}
    assert sum(v for _, v in samples(text, "purerest_circuit_breaker_calls_rejected_total")) == 1
    transitions = samples(text, "purerest_circuit_breaker_state_transitions_total")
    assert ({"from_state": "CLOSED", "to_state": "OPEN"}, 1.0) in [
        ({k: v for k, v in labels.items() if k != "otel_scope_name"}, value)
        for labels, value in transitions
    ]


def test_purekafka_and_purerest_metric_names_are_exported(
    kafka: KafkaBroker, lookup_stub: HttpStub, probe: Probe
) -> None:
    """After an event and a poison message: lag, event age (purekafka's buckets), DLQ
    count, retry attempts and the client request duration, with their label names.

    Source: ADR 0028 decision 8 (purekafka_consumer_lag,
    purekafka_consumer_event_age_seconds, purekafka_dlq_published_total);
    purekafka ConsumerLag, EventAge (buckets), DeadLetter, Retry; purerest
    ClientMetrics (http.client.request.duration), Retry (purerest.retry.attempts).
    """
    run = probe(PROBE_DLQ_MAX_RETRIES="0")
    kafka.produce(run.topic, "poison", "{", {})
    user_id = registered(kafka, run)
    wait_until(lambda: lookups(lookup_stub, user_id) == 1, "the lookup")
    wait_until(lambda: "purekafka_consumer_lag{" in run.scrape(), "the lag gauge")
    shapes = metric_shapes(run.scrape())
    expected = {
        "purekafka_consumer_lag": (
            "gauge",
            {
                "messaging_destination_name",
                "messaging_kafka_destination_partition",
                "messaging_consumer_group_name",
            },
        ),
        "purekafka_consumer_event_age_seconds": (
            "histogram",
            {"messaging_destination_name", "messaging_consumer_group_name"},
        ),
        "purekafka_dlq_published_total": ("counter", set()),
        "purekafka_retry_attempts_total": ("counter", {"outcome"}),
        "http_client_request_duration_seconds": (
            "histogram",
            {"http_request_method", "server_address", "http_response_status_code"},
        ),
        "purerest_retry_attempts_total": ("counter", {"outcome"}),
    }
    for name, (kind, labels) in expected.items():
        assert name in shapes, f"{name} missing: {sorted(shapes)}"
        got = (shapes[name].type, set(shapes[name].labels - {"otel_scope_name"}))
        assert got == (kind, labels), name
    assert shapes["purekafka_consumer_event_age_seconds"].buckets == EVENT_AGE_BUCKETS


def test_the_stream_restarts_after_a_broker_outage(
    kafka: KafkaBroker, lookup_stub: HttpStub, probe: Probe
) -> None:
    """With the broker gone the stream fails and is restarted with backoff, counted in
    purekafka_stream_restarts_total; once it is back, events flow again. (Runs last: it
    stops the session's broker.)

    Source: purekafka StreamSupervisor (restart indefinitely, base delay doubling to a
    cap, purekafka.stream.restarts); ADR 0028 decision 8.
    """
    run = probe(PROBE_RESTART_BASE_DELAY="200ms", PROBE_RESTART_MAX_DELAY="1s")
    first = registered(kafka, run)
    wait_until(lambda: lookups(lookup_stub, first) == 1, "the first event")
    kafka.stop()
    try:
        wait_until(
            lambda: (
                sum(v for _, v in samples(run.scrape(), "purekafka_stream_restarts_total")) >= 1
            ),
            "a counted restart",
            timeout_s=90,
        )
    finally:
        kafka.start()
    second = registered(kafka, run)
    wait_until(lambda: lookups(lookup_stub, second) == 1, "an event after the outage", timeout_s=90)
