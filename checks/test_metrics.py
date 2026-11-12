# SPDX-License-Identifier: MIT

"""Metrics (gluon PLAN.md RUST-1.7; ADR 0028 "Metrics" row; ADR 0027).

Reference: capture metrics.txt (the Scala service's scrape after the capture's
traffic): the families the generated dashboards query, their types, label
names and histogram buckets.
"""

from dataclasses import replace

import pytest
from support import new_email, post_credentials, signed_up

from gluon_contract.capture import capture_file
from gluon_contract.harness import Harness
from gluon_contract.http import request
from gluon_contract.metrics import metric_shapes, samples

pytestmark = pytest.mark.service("user-service")
"""user-service's contract: deselected in a run for another service (RPN-3)."""

SERVICE_FAMILIES = (
    "http_server_request_duration_seconds",
    "db_client_operation_duration_seconds",
    "db_client_connection_count",
    "db_client_connection_pending_requests",
    "db_client_connection_wait_time_seconds",
    "users_registrations_total",
    "users_logins_total",
)


def traffic(harness: Harness) -> str:
    """The capture's kinds of request: signup, duplicate, login, user reads; returns the userId."""
    email = new_email()
    user_id: str = signed_up(harness, email)["userId"]
    post_credentials(harness, "/auth/signup", email)
    post_credentials(harness, "/auth/login", email)
    request(harness.base_url, "GET", f"/users/{user_id}")
    request(harness.base_url, "GET", "/users/not-a-uuid")
    return user_id


def counter(harness: Harness, name: str, **labels: str) -> float:
    """The current value of a counter series (0 when absent)."""
    found = [
        value
        for got, value in samples(harness.scrape_metrics(), name)
        if labels.items() <= got.items()
    ]
    return sum(found)


def test_the_service_families_match_the_capture(harness: Harness) -> None:
    """Same names, types, label names and bucket boundaries as the Scala service exposes.

    Source: capture metrics.txt; ADR 0027 (dashboards query these families).
    """
    traffic(harness)
    expected = metric_shapes(capture_file("metrics.txt").read_text())
    actual = metric_shapes(harness.scrape_metrics())
    for name in SERVICE_FAMILIES:
        assert name in actual, f"{name} missing; exposed: {sorted(actual)}"
        got = actual[name]
        # A failed operation adds error_type (purerest ServerMetrics, UserStore
        # timed); the capture saw none, but a run that stops Postgres does.
        got = replace(got, labels=got.labels - {"error_type"})
        assert got == expected[name], name


def test_http_route_is_the_raw_path_with_uuid_segments_as_id(harness: Harness) -> None:
    """/users/<uuid> is recorded as /users/{id}; a malformed id keeps its raw path.

    Source: capture metrics.txt (http_route="/users/{id}", "/users/not-a-uuid");
    purerest ServerMetrics.routeTemplate.
    """
    traffic(harness)
    routes = {
        # .get: an unmatched path's series has no status code (another check's traffic).
        (
            labels["http_route"],
            labels["http_request_method"],
            labels.get("http_response_status_code"),
        )
        for labels, _ in samples(
            harness.scrape_metrics(), "http_server_request_duration_seconds_count"
        )
    }
    assert ("/users/{id}", "GET", "200") in routes, routes
    assert ("/users/not-a-uuid", "GET", "400") in routes, routes
    assert ("/auth/signup", "POST", "201") in routes, routes


def test_registrations_are_counted_by_outcome(harness: Harness) -> None:
    """users_registrations_total{outcome=created|duplicate}.

    Source: capture metrics.txt (outcome="created", "duplicate").
    """
    created = counter(harness, "users_registrations_total", outcome="created")
    duplicate = counter(harness, "users_registrations_total", outcome="duplicate")
    email = new_email()
    signed_up(harness, email)
    post_credentials(harness, "/auth/signup", email)
    assert counter(harness, "users_registrations_total", outcome="created") == created + 1
    assert counter(harness, "users_registrations_total", outcome="duplicate") == duplicate + 1


def test_successful_logins_are_counted(harness: Harness) -> None:
    """users_logins_total counts successful logins only.

    Source: capture metrics.txt (users_logins_total); ADR 0027 ("Registrations + logins").
    """
    email = new_email()
    signed_up(harness, email)
    before = counter(harness, "users_logins_total")
    assert post_credentials(harness, "/auth/login", email, "wrong-password-1").status == 401
    assert post_credentials(harness, "/auth/login", email).status == 200
    assert counter(harness, "users_logins_total") == before + 1


def http_series(harness: Harness) -> list[dict[str, str]]:
    """The label sets of every HTTP server duration series."""
    return [
        labels
        for labels, _ in samples(
            harness.scrape_metrics(), "http_server_request_duration_seconds_count"
        )
    ]


def test_a_segment_is_an_id_when_java_would_parse_it_as_a_uuid(harness: Harness) -> None:
    """http_route collapses a segment java.util.UUID.fromString accepts, however short.

    Source: purerest ServerMetrics.routeTemplate (allCatch.opt(UUID.fromString)),
    checked against the JDK. Implicit behaviour (RUST-1.9).
    """
    request(harness.base_url, "GET", "/users/1-2-3-4-5")
    request(harness.base_url, "GET", "/users/0123456789abcdef0123456789abcdef")
    routes = {(s["http_route"], s.get("http_response_status_code")) for s in http_series(harness)}
    assert ("/users/{id}", "404") in routes, routes
    assert ("/users/0123456789abcdef0123456789abcdef", "400") in routes, routes


def test_an_unmatched_path_is_recorded_without_a_status_code(harness: Harness) -> None:
    """The 404 for a path no route matches comes from outside the metered routes.

    Source: capture metrics.txt (http_route="/no-such-path" with no
    http_response_status_code); purerest ServerMetrics (status code only when
    the route matched). Implicit behaviour (RUST-1.9).
    """
    assert request(harness.base_url, "GET", "/no-such-path").status == 404
    series = [s for s in http_series(harness) if s["http_route"] == "/no-such-path"]
    assert series, http_series(harness)
    assert all("http_response_status_code" not in s for s in series), series


def test_a_cors_preflight_is_not_recorded(harness: Harness) -> None:
    """CORS answers a preflight outside the metered routes: no OPTIONS series.

    Source: capture metrics.txt (no OPTIONS series, though the capture sent a
    preflight); user-service AppRoutes (CORS wraps the metered routes).
    Implicit behaviour (RUST-1.9).
    """
    preflight = request(
        harness.base_url,
        "OPTIONS",
        "/auth/signup",
        headers={"Origin": "http://example.com", "Access-Control-Request-Method": "POST"},
    )
    assert preflight.status == 200
    assert [s for s in http_series(harness) if s["http_request_method"] == "OPTIONS"] == []
