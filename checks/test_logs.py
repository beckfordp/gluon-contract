# SPDX-License-Identifier: MIT

"""Logs (gluon PLAN.md RUST-1.7; ADR 0028 "Logs" row).

Reference: capture stdout.log (logstash-logback-encoder JSON lines), gluon
infra/k8s/observability/config/filebeat.yml (only lines starting
{"@timestamp" are decoded), product-guidelines (no secrets in logs).
"""

import json
import re
from collections.abc import Callable
from typing import Any

import pytest
from support import JSON, new_email, new_traceparent, post_credentials, signed_up

from gluon_contract.formats import parse_traceparent
from gluon_contract.harness import Harness
from gluon_contract.http import request

BASE_FIELDS = (
    "@timestamp",
    "@version",
    "message",
    "logger_name",
    "thread_name",
    "level",
    "level_value",
)
LEVELS = {"TRACE": 5000, "DEBUG": 10000, "INFO": 20000, "WARN": 30000, "ERROR": 40000}


def json_lines(harness: Harness) -> list[dict[str, Any]]:
    """Every line Filebeat would decode."""
    return [json.loads(line) for line in harness.log_lines() if line.startswith('{"@timestamp"')]


def test_json_lines_have_the_logstash_fields(harness: Harness) -> None:
    """@timestamp first, then the base fields; @version "1"; level_value matches level.

    Source: capture stdout.log; filebeat.yml ('^\\{"@timestamp"').
    """
    signed_up(harness, new_email())
    harness.target.wait_for_log(lambda line: '"Account created"' in line)
    lines = json_lines(harness)
    assert lines, "no JSON log lines"
    for line in lines:
        assert list(line)[: len(BASE_FIELDS)][0] == "@timestamp", line
        assert set(BASE_FIELDS) <= set(line), line
        assert line["@version"] == "1"
        assert line["level_value"] == LEVELS[line["level"]], line


def test_the_startup_line_names_the_ports(harness: Harness) -> None:
    """ "user-service starting" with port and metrics_port.

    Source: capture stdout.log ({"message": "user-service starting", "port", "metrics_port"}).
    """
    line = json.loads(harness.target.wait_for_log(lambda text: '"user-service starting"' in text))
    assert (line["port"], line["metrics_port"]) == (
        str(harness.endpoints.http_port),
        str(harness.endpoints.metrics_port),
    )


def test_request_lines_carry_method_path_and_the_request_span(harness: Harness) -> None:
    """ "Received request" with method, path, trace_id and span_id of the SERVER span.

    Source: capture stdout.log (request lines: method, path, trace_id, span_id).
    """
    inbound = new_traceparent()
    parts = parse_traceparent(inbound)
    assert parts is not None
    signed_up(harness, new_email(), traceparent=inbound)
    (server,) = harness.otlp.wait_for_spans(
        lambda s: s.trace_id == parts.trace_id and s.name == "POST /auth/signup", timeout_s=20
    )
    line = json.loads(
        harness.target.wait_for_log(
            lambda text: parts.trace_id in text and '"Received request"' in text
        )
    )
    assert (line["method"], line["path"], line["trace_id"], line["span_id"]) == (
        "POST",
        "/auth/signup",
        parts.trace_id,
        server.span_id,
    )


def test_no_password_or_token_is_ever_logged(harness: Harness) -> None:
    """Neither the plaintext password nor any issued token appears in the output.

    Source: product-guidelines ("Passwords are never stored, logged"; "never log token values").
    """
    email, password = new_email(), "a-password-nobody-logs-1"
    signup = signed_up(harness, email, password=password)
    login = post_credentials(harness, "/auth/login", email, password).json()
    harness.target.wait_for_log(lambda line: '"Login succeeded"' in line)
    output = "\n".join(harness.log_lines())
    for secret in (password, signup["token"], login["token"], login["refreshToken"]):
        assert secret not in output


TIMESTAMP = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d*[1-9])?Z$")


def test_timestamps_are_utc_with_the_fraction_trimmed(harness: Harness) -> None:
    """ISO-8601 in UTC ("Z"), the fraction without trailing zeros (20.75179Z).

    Source: capture stdout.log; logstash-logback-encoder's default
    ISO_OFFSET_DATE_TIME in a UTC container. Implicit behaviour (RUST-1.9).
    """
    signed_up(harness, new_email())
    harness.target.wait_for_log(lambda line: '"Account created"' in line)
    for line in json_lines(harness):
        assert TIMESTAMP.match(line["@timestamp"]), line["@timestamp"]


def trace_lines(harness: Harness, trace_id: str, last: str) -> list[dict[str, Any]]:
    """The trace's JSON lines once its line with message `last` has been written."""
    harness.target.wait_for_log(lambda text: trace_id in text and f'"{last}"' in text)
    return [line for line in json_lines(harness) if line.get("trace_id") == trace_id]


def shape(line: dict[str, Any]) -> tuple[str, str, tuple[str, ...]]:
    """(message, level, the names of the fields beyond the base ones)."""
    extra = tuple(sorted(set(line) - set(BASE_FIELDS)))
    return line["message"], line["level"], extra


def existing_user(harness: Harness) -> tuple[str, str]:
    """A fresh account: (email, userId)."""
    email = new_email()
    return email, signed_up(harness, email)["userId"]


REQUEST = ("method", "path", "span_id", "trace_id")
WITH_USER = ("method", "path", "span_id", "trace_id", "user_id")
WITH_ERROR = ("error", "method", "path", "span_id", "trace_id")
Scenario = Callable[[Harness, str], str | None]


def signup_created(harness: Harness, traceparent: str) -> str | None:
    """A new account; returns its userId."""
    return str(signed_up(harness, new_email(), traceparent=traceparent)["userId"])


def signup_duplicate(harness: Harness, traceparent: str) -> str | None:
    """The same address again."""
    email, _ = existing_user(harness)
    post_credentials(harness, "/auth/signup", email, traceparent=traceparent)
    return None


def signup_invalid_email(harness: Harness, traceparent: str) -> str | None:
    """An address that isn't one."""
    post_credentials(harness, "/auth/signup", "not-an-email", traceparent=traceparent)
    return None


def signup_short_password(harness: Harness, traceparent: str) -> str | None:
    """A password under 8 characters."""
    post_credentials(harness, "/auth/signup", new_email(), "short", traceparent=traceparent)
    return None


def login_empty_password(harness: Harness, traceparent: str) -> str | None:
    """No password."""
    post_credentials(harness, "/auth/login", new_email(), "", traceparent=traceparent)
    return None


def login_wrong_password(harness: Harness, traceparent: str) -> str | None:
    """A registered address, the wrong password."""
    email, _ = existing_user(harness)
    post_credentials(harness, "/auth/login", email, "wrong-password-1", traceparent=traceparent)
    return None


def login_succeeded(harness: Harness, traceparent: str) -> str | None:
    """The right password; returns the userId."""
    email, user_id = existing_user(harness)
    post_credentials(harness, "/auth/login", email, traceparent=traceparent)
    return user_id


def user_found(harness: Harness, traceparent: str) -> str | None:
    """GET an existing user; returns its id."""
    _, user_id = existing_user(harness)
    request(harness.base_url, "GET", f"/users/{user_id}", headers={"traceparent": traceparent})
    return user_id


def user_not_found(harness: Harness, traceparent: str) -> str | None:
    """GET an id nobody has."""
    path = "/users/00000000-0000-0000-0000-000000000000"
    request(harness.base_url, "GET", path, headers={"traceparent": traceparent})
    return "00000000-0000-0000-0000-000000000000"


ERRORS = {
    "signup_invalid_email": "Enter a valid email address",
    "signup_short_password": "Password must be at least 8 characters",
    "login_empty_password": "Enter your password",
}
"""The `error` field: the response's error text (AuthRoutes.message)."""


OUTCOMES: list[tuple[Scenario, list[tuple[str, str, tuple[str, ...]]]]] = [
    (signup_created, [("Account created", "INFO", WITH_USER)]),
    (signup_duplicate, [("Duplicate signup", "WARN", REQUEST)]),
    (signup_invalid_email, [("Invalid signup request", "WARN", WITH_ERROR)]),
    (signup_short_password, [("Invalid signup request", "WARN", WITH_ERROR)]),
    (login_empty_password, [("Invalid login request", "WARN", WITH_ERROR)]),
    (login_wrong_password, [("Login failed", "WARN", REQUEST)]),
    (login_succeeded, [("Login succeeded", "INFO", WITH_USER)]),
    (user_found, [("Request completed", "INFO", WITH_USER)]),
    (user_not_found, [("User not found", "WARN", WITH_USER)]),
]


@pytest.mark.parametrize(
    ("scenario", "expected"), OUTCOMES, ids=[scenario.__name__ for scenario, _ in OUTCOMES]
)
def test_each_outcome_logs_its_message_at_its_level(
    harness: Harness, scenario: Scenario, expected: list[tuple[str, str, tuple[str, ...]]]
) -> None:
    """ "Received request", then one line naming the outcome, in the request's trace.

    Source: capture stdout.log (messages, levels and fields of every user-service
    line); user-service AuthRoutes and UserRoutes (the context maps, the error
    text). Implicit behaviour (RUST-1.9): Kibana searches use these messages.
    """
    inbound = new_traceparent()
    parts = parse_traceparent(inbound)
    assert parts is not None
    user_id = scenario(harness, inbound)
    lines = trace_lines(harness, parts.trace_id, expected[-1][0])
    first = "Received request", "INFO", (WITH_USER if "/users/" in lines[0]["path"] else REQUEST)
    assert [shape(line) for line in lines] == [first, *expected], lines
    if user_id is not None:
        assert all(line["user_id"] == user_id for line in lines if "user_id" in line), lines
    if scenario.__name__ in ERRORS:
        assert lines[-1]["error"] == ERRORS[scenario.__name__], lines[-1]


def test_a_user_path_is_logged_with_the_canonical_id(harness: Harness) -> None:
    """GET /users/<UPPER-CASE id> logs path and user_id with the id lower-cased.

    Source: capture stdout.log (the upper-case request of
    http/users-200-uppercase-id.txt logged as "/users/691b03e8-…"); user-service
    UserRoutes (path s"/users/$renderedId"). Implicit behaviour (RUST-1.9).
    """
    _, user_id = existing_user(harness)
    inbound = new_traceparent()
    parts = parse_traceparent(inbound)
    assert parts is not None
    request(harness.base_url, "GET", f"/users/{user_id.upper()}", headers={"traceparent": inbound})
    lines = trace_lines(harness, parts.trace_id, "Request completed")
    assert {(line["path"], line["user_id"]) for line in lines} == {(f"/users/{user_id}", user_id)}


def test_a_request_that_fails_to_decode_logs_nothing(harness: Harness) -> None:
    """Malformed JSON and a malformed id never reach the handler: no line.

    Source: capture stdout.log (7 "Received request" lines for 11 signup spans:
    the 4 undecodable bodies logged nothing). Implicit behaviour (RUST-1.9).
    """
    inbound = new_traceparent()
    parts = parse_traceparent(inbound)
    assert parts is not None
    headers = {**JSON, "traceparent": inbound}
    request(harness.base_url, "POST", "/auth/signup", body=b"{not json", headers=headers)
    request(harness.base_url, "GET", "/users/not-a-uuid", headers={"traceparent": inbound})
    marker = new_traceparent()
    marker_parts = parse_traceparent(marker)
    assert marker_parts is not None
    signed_up(harness, new_email(), traceparent=marker)
    trace_lines(harness, marker_parts.trace_id, "Account created")
    assert [line for line in json_lines(harness) if line.get("trace_id") == parts.trace_id] == []
