# SPDX-License-Identifier: MIT

"""The env-var contract a service is started with (RUST-1.2 spec FR2; RPN-3 FR3).

Source: each service's `src/main/resources/application.conf` (the `${?VAR}`
overrides) and gluon `environments/local/<service>.values.yaml`.
"""

from pathlib import Path

import pytest
import yaml

from gluon_contract.env_contract import (
    BASE_VARIABLES,
    Endpoints,
    MissingEndpointError,
    PostgresLogin,
    postgres_login,
    service_env,
    variable_prefix,
)
from gluon_contract.services import KNOWN_SERVICES, UnknownServiceError

GLUON_LOCAL = Path(__file__).resolve().parents[4] / "environments" / "local"

ENDPOINTS = Endpoints(
    http_port=18080,
    metrics_port=19090,
    postgres_host="127.0.0.1",
    postgres_port=15432,
    otlp_endpoint="http://127.0.0.1:14318",
)
NOTIFICATION_ENDPOINTS = Endpoints(
    http_port=18080,
    metrics_port=19090,
    postgres_host="127.0.0.1",
    postgres_port=15432,
    otlp_endpoint="http://127.0.0.1:14318",
    kafka_bootstrap="127.0.0.1:19092",
    service_urls={
        "user-service": "http://127.0.0.1:18091",
        "order-service": "http://127.0.0.1:18092",
    },
)


def test_user_service_gets_exactly_its_contract_variables() -> None:
    """The variables user-service reads, with the values the harness chose."""
    env = service_env("user-service", ENDPOINTS, base_env={})
    assert env == {
        "USER_SERVICE_PORT": "18080",
        "USER_SERVICE_METRICS_PORT": "19090",
        "POSTGRES_HOST": "127.0.0.1",
        "POSTGRES_PORT": "15432",
        "POSTGRES_DB": "user",
        "POSTGRES_USER": "user",
        "POSTGRES_PASSWORD": "user",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:14318",
    }


def test_user_service_ignores_endpoints_it_has_no_use_for() -> None:
    """A broker or service URLs the harness has don't reach user-service: it reads neither."""
    assert service_env("user-service", NOTIFICATION_ENDPOINTS, base_env={}) == service_env(
        "user-service", ENDPOINTS, base_env={}
    )


def test_notification_service_gets_exactly_its_contract_variables() -> None:
    """The common variables under its own names, its database, the broker and the two
    services it calls; nothing else.

    Source: notification-service application.conf (NOTIFICATION_SERVICE_PORT,
    NOTIFICATION_SERVICE_METRICS_PORT, postgres "notification", KAFKA_BOOTSTRAP_SERVERS,
    USER_SERVICE_URL, ORDER_SERVICE_URL); environments/local/notification-service.values.yaml.
    """
    env = service_env("notification-service", NOTIFICATION_ENDPOINTS, base_env={})
    assert env == {
        "NOTIFICATION_SERVICE_PORT": "18080",
        "NOTIFICATION_SERVICE_METRICS_PORT": "19090",
        "POSTGRES_HOST": "127.0.0.1",
        "POSTGRES_PORT": "15432",
        "POSTGRES_DB": "notification",
        "POSTGRES_USER": "notification",
        "POSTGRES_PASSWORD": "notification",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:14318",
        "KAFKA_BOOTSTRAP_SERVERS": "127.0.0.1:19092",
        "USER_SERVICE_URL": "http://127.0.0.1:18091",
        "ORDER_SERVICE_URL": "http://127.0.0.1:18092",
    }


def test_notification_service_without_a_broker_is_an_error() -> None:
    """It can't be started without KAFKA_BOOTSTRAP_SERVERS: the harness must start a broker."""
    with pytest.raises(MissingEndpointError, match="KAFKA_BOOTSTRAP_SERVERS"):
        service_env("notification-service", ENDPOINTS, base_env={})


def test_notification_service_without_a_called_service_is_an_error() -> None:
    """Each service it calls needs an address: ORDER_SERVICE_URL here."""
    endpoints = Endpoints(
        http_port=18080,
        metrics_port=19090,
        postgres_host="127.0.0.1",
        postgres_port=15432,
        otlp_endpoint="http://127.0.0.1:14318",
        kafka_bootstrap="127.0.0.1:19092",
        service_urls={"user-service": "http://127.0.0.1:18091"},
    )
    with pytest.raises(MissingEndpointError, match="ORDER_SERVICE_URL"):
        service_env("notification-service", endpoints, base_env={})


@pytest.mark.parametrize(
    ("service", "port_variable", "domain"),
    [
        ("user-service", "USER_SERVICE_PORT", "user"),
        ("notification-service", "NOTIFICATION_SERVICE_PORT", "notification"),
    ],
)
def test_variable_names_follow_the_service_name(
    service: str, port_variable: str, domain: str
) -> None:
    """`<DOMAIN>_SERVICE_*` and the domain-named database, as every gluon service."""
    env = service_env(service, NOTIFICATION_ENDPOINTS, base_env={})
    assert env[port_variable] == "18080"
    assert env["POSTGRES_DB"] == domain


def test_a_service_the_harness_has_no_profile_for_is_an_error() -> None:
    """order-service follows the naming, but what else it needs isn't known yet."""
    with pytest.raises(UnknownServiceError, match="order-service"):
        service_env("order-service", ENDPOINTS, base_env={})


def test_only_the_minimal_base_passes_through_from_the_harness_environment() -> None:
    """PATH, HOME, LANG, TZ and JAVA_HOME pass through; nothing else leaks in."""
    base = {
        "PATH": "/usr/bin",
        "HOME": "/home/model",
        "LANG": "C.UTF-8",
        "TZ": "UTC",
        "JAVA_HOME": "/usr/lib/jvm/java-21",
        "CONTRACT_TARGET_CMD": "svc",
        "AUTH_PBKDF2_ITERATIONS": "1",
        "OTEL_TRACES_SAMPLER_ARG": "0.5",
    }
    env = service_env("user-service", ENDPOINTS, base_env=base)
    for name in ("PATH", "HOME", "LANG", "TZ", "JAVA_HOME"):
        assert env[name] == base[name]
    for leaked in ("CONTRACT_TARGET_CMD", "AUTH_PBKDF2_ITERATIONS", "OTEL_TRACES_SAMPLER_ARG"):
        assert leaked not in env
    notification = service_env(
        "notification-service",
        NOTIFICATION_ENDPOINTS,
        base_env={**base, "KAFKA_BOOTSTRAP_SERVERS": "kafka:9092", "USER_SERVICE_URL": "x"},
    )
    assert notification["KAFKA_BOOTSTRAP_SERVERS"] == "127.0.0.1:19092"
    assert notification["USER_SERVICE_URL"] == "http://127.0.0.1:18091"
    assert "CONTRACT_TARGET_CMD" not in notification
    assert set(BASE_VARIABLES) == {"PATH", "HOME", "LANG", "TZ", "JAVA_HOME"}


def test_absent_base_variables_are_simply_absent() -> None:
    """A base variable the harness doesn't have isn't invented."""
    env = service_env("user-service", ENDPOINTS, base_env={"PATH": "/usr/bin"})
    assert "JAVA_HOME" not in env
    assert env["PATH"] == "/usr/bin"


def test_postgres_login_is_the_domain_name_throughout() -> None:
    """Database, user and password are all the domain, as in gluon-local's manifests."""
    assert postgres_login("user-service") == PostgresLogin(
        database="user", user="user", password="user"
    )
    assert postgres_login("notification-service") == PostgresLogin(
        database="notification", user="notification", password="notification"
    )


@pytest.mark.parametrize("service", KNOWN_SERVICES)
def test_the_variables_are_the_ones_gluon_local_sets(service: str) -> None:
    """The names gluon-local's values file sets, plus the service's two ports (the chart
    sets them) and POSTGRES_PORT (gluon-local uses the default; the harness a free port)."""
    values = yaml.safe_load((GLUON_LOCAL / f"{service}.values.yaml").read_text(encoding="utf-8"))
    prefix = variable_prefix(service)
    expected = {entry["name"] for entry in values["env"]} | {
        f"{prefix}_PORT",
        f"{prefix}_METRICS_PORT",
        "POSTGRES_PORT",
    }
    assert set(service_env(service, NOTIFICATION_ENDPOINTS, base_env={})) == expected
