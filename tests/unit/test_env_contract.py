# SPDX-License-Identifier: MIT

"""The env-var contract a service is started with (RUST-1.2 spec FR2).

Source: user-service `src/main/resources/application.conf` (the `${?VAR}`
overrides) and gluon `environments/local/user-service.values.yaml`.
"""

import pytest

from gluon_contract.env_contract import (
    BASE_VARIABLES,
    Endpoints,
    PostgresLogin,
    postgres_login,
    service_env,
)

ENDPOINTS = Endpoints(
    http_port=18080,
    metrics_port=19090,
    postgres_host="127.0.0.1",
    postgres_port=15432,
    otlp_endpoint="http://127.0.0.1:14318",
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


@pytest.mark.parametrize(
    ("service", "port_variable", "domain"),
    [
        ("order-service", "ORDER_SERVICE_PORT", "order"),
        ("fulfilment-service", "FULFILMENT_SERVICE_PORT", "fulfilment"),
    ],
)
def test_variable_names_follow_the_service_name(
    service: str, port_variable: str, domain: str
) -> None:
    """`<DOMAIN>_SERVICE_*` and the domain-named database, as every gluon service."""
    env = service_env(service, ENDPOINTS, base_env={})
    assert env[port_variable] == "18080"
    assert env["POSTGRES_DB"] == domain


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
