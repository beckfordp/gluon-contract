# SPDX-License-Identifier: MIT

"""What the harness starts for each service besides Postgres and the OTLP stub (RPN-3).

A service's profile names its dependencies as gluon-local gives them: a Kafka
broker (and the topics it consumes, created before it starts), and the services
it calls over HTTP. The harness starts a broker and a stub for each; the env
contract (`env_contract.py`) points the service at them.

Sources: each service's `src/main/resources/application.conf` (the `${?VAR}`
overrides) and gluon `environments/local/<service>.values.yaml`; for
notification-service's topics, the capture's `CAPTURE.sh`
(`contracts/notification-service/20261111/`).
"""

from dataclasses import dataclass


class UnknownServiceError(Exception):
    """The harness has no profile for the service, so it can't start it."""


@dataclass(frozen=True, slots=True)
class ServiceProfile:
    """One service's dependencies beyond Postgres and the OTLP stub."""

    name: str
    kafka: bool = False
    """Reads `KAFKA_BOOTSTRAP_SERVERS`: the harness starts a broker."""
    topics: tuple[str, ...] = ()
    """The topics it consumes, created on that broker before it starts."""
    calls: tuple[str, ...] = ()
    """The services it calls: each is stubbed, its `<DOMAIN>_SERVICE_URL` pointing there."""


PROFILES = (
    # Its outbox reaches Kafka through Debezium (the CDC group's stack), not a client.
    ServiceProfile(name="user-service"),
    # application.conf: kafka.bootstrap-servers, user-client, order-client (ADR 0025).
    ServiceProfile(
        name="notification-service",
        kafka=True,
        topics=("user-events", "order-events", "payment-events", "fulfilment-events"),
        calls=("user-service", "order-service"),
    ),
)

KNOWN_SERVICES = tuple(known.name for known in PROFILES)
"""The services a run can judge; the first is the default."""


def profile(service: str) -> ServiceProfile:
    """The profile of `service`.

    Raises:
        UnknownServiceError: naming the services the harness knows.
    """
    for known in PROFILES:
        if known.name == service:
            return known
    raise UnknownServiceError(
        f"the harness has no profile for {service!r} (it knows {', '.join(KNOWN_SERVICES)}); "
        "add one to gluon_contract/services.py"
    )
