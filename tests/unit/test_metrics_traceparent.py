# SPDX-License-Identifier: MIT

"""Metric shapes and traceparent parsing (RUST-1.7 helpers)."""

import pytest

from gluon_contract.capture import capture_file
from gluon_contract.formats import parse_traceparent
from gluon_contract.metrics import metric_shapes, samples

TEXT = """# TYPE users_registrations_total counter
users_registrations_total{outcome="created",otel_scope_name="user-service"} 3.0
users_registrations_total{outcome="duplicate",otel_scope_name="user-service"} 1.0
# TYPE http_server_request_duration_seconds histogram
http_server_request_duration_seconds_bucket{http_route="/users/{id}",le="0.005"} 1
http_server_request_duration_seconds_bucket{http_route="/users/{id}",le="+Inf"} 1
http_server_request_duration_seconds_count{http_route="/users/{id}"} 1
http_server_request_duration_seconds_sum{http_route="/users/{id}"} 0.001
"""


def test_shapes_have_type_label_names_and_buckets() -> None:
    """Counters keep their _total name; histograms list their le boundaries."""
    shapes = metric_shapes(TEXT)
    counter = shapes["users_registrations_total"]
    assert (counter.type, counter.labels, counter.buckets) == (
        "counter",
        frozenset({"outcome", "otel_scope_name"}),
        (),
    )
    histogram = shapes["http_server_request_duration_seconds"]
    assert histogram.type == "histogram"
    assert histogram.labels == frozenset({"http_route"})
    assert histogram.buckets == (0.005, float("inf"))


def test_samples_by_name() -> None:
    """Each sample's labels and value."""
    assert samples(TEXT, "users_registrations_total") == [
        ({"outcome": "created", "otel_scope_name": "user-service"}, 3.0),
        ({"outcome": "duplicate", "otel_scope_name": "user-service"}, 1.0),
    ]


def test_the_captured_metrics_parse() -> None:
    """The capture's service families are there with their labels."""
    shapes = metric_shapes(capture_file("metrics.txt").read_text())
    assert "otel_scope_name" in shapes["users_logins_total"].labels
    assert len(shapes["db_client_operation_duration_seconds"].buckets) > 10


def test_traceparent_parts() -> None:
    """W3C version-00 traceparent: trace id, span id, flags; anything else is None."""
    parts = parse_traceparent("00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-03")
    assert parts is not None
    assert (parts.trace_id, parts.span_id, parts.sampled) == (
        "0af7651916cd43dd8448eb211c80319c",
        "b7ad6b7169203331",
        True,
    )
    unsampled = parse_traceparent("00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-00")
    assert unsampled is not None
    assert unsampled.sampled is False
    assert parse_traceparent("garbage") is None
    with pytest.raises(FileNotFoundError):
        capture_file("no-such-file.txt")
