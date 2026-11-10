# SPDX-License-Identifier: MIT

"""The consumer probe's env contract (RUST-6.5)."""

from gluon_contract.probe import DEFAULTS, probe_env


def test_the_probe_gets_its_broker_topic_group_lookup_and_ports() -> None:
    """Everything it needs to find, and nothing from the harness's own environment."""
    env = probe_env(
        bootstrap="127.0.0.1:59092",
        topic="user-events-abc",
        group="events-probe-abc",
        lookup_url="http://127.0.0.1:5000",
        metrics_port=59090,
        otlp_endpoint="http://127.0.0.1:4318",
        base_env={"PATH": "/usr/bin", "HOME": "/home/x", "SECRET": "no"},
    )
    assert env["PROBE_KAFKA_BOOTSTRAP"] == "127.0.0.1:59092"
    assert env["PROBE_TOPIC"] == "user-events-abc"
    assert env["PROBE_GROUP_ID"] == "events-probe-abc"
    assert env["PROBE_LOOKUP_URL"] == "http://127.0.0.1:5000"
    assert env["PROBE_METRICS_PORT"] == "59090"
    assert env["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://127.0.0.1:4318"
    assert env["PATH"] == "/usr/bin"
    assert "SECRET" not in env


def test_resilience_defaults_are_notification_services_and_overridable() -> None:
    """notification-service application.conf: dlq-retry 3 at 200ms, user-client retry 3 at
    100ms, breaker 5 / 30s, stream supervisor 1s..30s, request timeout 5s."""
    assert DEFAULTS == {
        "PROBE_LOOKUP_TIMEOUT": "5s",
        "PROBE_LOOKUP_MAX_RETRIES": "3",
        "PROBE_LOOKUP_BASE_DELAY": "100ms",
        "PROBE_BREAKER_FAILURE_THRESHOLD": "5",
        "PROBE_BREAKER_RESET_TIMEOUT": "30s",
        "PROBE_DLQ_MAX_RETRIES": "3",
        "PROBE_DLQ_BASE_DELAY": "200ms",
        "PROBE_RESTART_BASE_DELAY": "1s",
        "PROBE_RESTART_MAX_DELAY": "30s",
        "PROBE_LAG_INTERVAL": "1s",
    }
    env = probe_env(
        bootstrap="b",
        topic="t",
        group="g",
        lookup_url="u",
        metrics_port=1,
        otlp_endpoint="o",
        base_env={},
        PROBE_LOOKUP_MAX_RETRIES="0",
    )
    assert env["PROBE_LOOKUP_MAX_RETRIES"] == "0"
    assert env["PROBE_DLQ_MAX_RETRIES"] == "3"
