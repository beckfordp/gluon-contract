# SPDX-License-Identifier: MIT

"""The env-var contract a service is started with (RUST-1.2 spec FR2; RPN-3 FR3).

Source: each service's `src/main/resources/application.conf`, whose `${?VAR}`
overrides name the variables, and gluon `environments/local/<service>.values.yaml`,
which sets them in gluon-local. Every generated gluon service follows the same
`<DOMAIN>_SERVICE_*` and domain-named-database pattern; what a service needs
beyond that (a broker, the services it calls) is its profile (`services.py`).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

from gluon_contract.services import profile

BASE_VARIABLES = ("PATH", "HOME", "LANG", "TZ", "JAVA_HOME")
"""Passed through from the harness so the process can run at all; nothing else is."""

KAFKA_VARIABLE = "KAFKA_BOOTSTRAP_SERVERS"
"""Where a service that reads Kafka finds its broker (gluon-local: `kafka:9092`)."""


class MissingEndpointError(ValueError):
    """The service needs a dependency the harness gave no address for."""


@dataclass(frozen=True, slots=True)
class Endpoints:
    """Where the harness put the service's ports and dependencies."""

    http_port: int
    metrics_port: int
    postgres_host: str
    postgres_port: int
    otlp_endpoint: str
    kafka_bootstrap: str | None = None
    """The broker, for a service that reads Kafka."""
    service_urls: Mapping[str, str] = field(default_factory=dict)
    """The stub standing in for each service it calls, by service name."""


@dataclass(frozen=True, slots=True)
class PostgresLogin:
    """The database and credentials a service expects, as gluon-local sets them."""

    database: str
    user: str
    password: str


def domain_of(service: str) -> str:
    """`user-service` → `user`."""
    return service.removesuffix("-service")


def variable_prefix(service: str) -> str:
    """`notification-service` → `NOTIFICATION_SERVICE`: its variables' prefix."""
    return domain_of(service).upper().replace("-", "_") + "_SERVICE"


def postgres_login(service: str) -> PostgresLogin:
    """Database, user and password are all the domain name, as in gluon-local."""
    domain = domain_of(service)
    return PostgresLogin(database=domain, user=domain, password=domain)


def service_env(
    service: str, endpoints: Endpoints, *, base_env: Mapping[str, str]
) -> dict[str, str]:
    """The complete environment to start `service` with.

    Args:
        service: the service name, e.g. `user-service`.
        endpoints: the ports and dependency addresses the harness chose.
        base_env: the harness's own environment; only `BASE_VARIABLES` are taken.

    Raises:
        UnknownServiceError: the harness has no profile for `service`.
        MissingEndpointError: `endpoints` lacks a dependency the service reads.
    """
    needs = profile(service)
    prefix = variable_prefix(service)
    login = postgres_login(service)
    env = {name: base_env[name] for name in BASE_VARIABLES if name in base_env}
    env.update(
        {
            f"{prefix}_PORT": str(endpoints.http_port),
            f"{prefix}_METRICS_PORT": str(endpoints.metrics_port),
            "POSTGRES_HOST": endpoints.postgres_host,
            "POSTGRES_PORT": str(endpoints.postgres_port),
            "POSTGRES_DB": login.database,
            "POSTGRES_USER": login.user,
            "POSTGRES_PASSWORD": login.password,
            "OTEL_EXPORTER_OTLP_ENDPOINT": endpoints.otlp_endpoint,
        }
    )
    if needs.kafka:
        if endpoints.kafka_bootstrap is None:
            raise MissingEndpointError(f"{service} reads {KAFKA_VARIABLE}: no broker was given")
        env[KAFKA_VARIABLE] = endpoints.kafka_bootstrap
    for called in needs.calls:
        variable = f"{variable_prefix(called)}_URL"
        if called not in endpoints.service_urls:
            raise MissingEndpointError(f"{service} reads {variable}: no stub for {called}")
        env[variable] = endpoints.service_urls[called]
    return env
