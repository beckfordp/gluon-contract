# SPDX-License-Identifier: MIT

"""The consumer probe as the probe group runs it (RUST-6.5; ADR 0028 decision 8).

The probe (`services/user-service-rs`, crate `events-probe`) is never deployed:
it only runs here, on its own topic and consumer group on the session's
broker, calling the check's lookup stub, exporting to its own OTLP stub. Its
env contract is the probe's own (documented in its README); the resilience
defaults are notification-service's (`application.conf`), which the probe
stands in for.
"""

from collections.abc import Mapping

BASE_VARIABLES = ("PATH", "HOME", "LANG", "LC_ALL", "TZ", "LLVM_PROFILE_FILE")
"""Taken from the harness's environment; nothing else leaks in."""

DEFAULTS = {
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
"""notification-service's settings (dlq-retry, user-client resilience,
stream-supervisor, the 5 s request timeout); the lag poll every second here,
so a check needn't wait."""


def probe_env(
    *,
    bootstrap: str,
    topic: str,
    group: str,
    lookup_url: str,
    metrics_port: int,
    otlp_endpoint: str,
    base_env: Mapping[str, str],
    **overrides: str,
) -> dict[str, str]:
    """The probe's complete environment."""
    env = {name: base_env[name] for name in BASE_VARIABLES if name in base_env}
    env.update(DEFAULTS)
    env.update(
        {
            "PROBE_KAFKA_BOOTSTRAP": bootstrap,
            "PROBE_TOPIC": topic,
            "PROBE_GROUP_ID": group,
            "PROBE_LOOKUP_URL": lookup_url,
            "PROBE_METRICS_PORT": str(metrics_port),
            "PROBE_SERVICE_NAME": "events-probe",
            "OTEL_EXPORTER_OTLP_ENDPOINT": otlp_endpoint,
        }
    )
    env.update(overrides)
    return env
