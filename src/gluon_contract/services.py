# SPDX-License-Identifier: MIT

"""Each service as the harness knows it (RPN-3, gluon TD-44): its capture, and what the
harness starts for it besides Postgres and the OTLP stub.

A service's profile names its dependencies as gluon-local gives them: a Kafka
broker (and the topics it consumes, created before it starts), and the services
it calls over HTTP. The harness starts a broker and a stub for each; the env
contract (`env_contract.py`) points the service at them.

Sources: each service's `src/main/resources/application.conf` (the `${?VAR}`
overrides) and gluon `environments/local/<service>.values.yaml`; for
notification-service's topics, the capture's `CAPTURE.sh`
(`contracts/notification-service/20261111/`).
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from gluon_contract.contracts import CONTRACTS_ROOT, latest_capture
from gluon_contract.http_stub import Answer, no_answer


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
    """The services it calls: each is stubbed, its `<prefix>_URL` pointing there."""
    prefix: str | None = None
    """Its variables' prefix (`<prefix>_PORT`, `<prefix>_URL`), if not `<DOMAIN>_SERVICE`."""
    stub: Answer = no_answer
    """How a stub standing in for it answers, for a service that calls it."""

    def capture(self, root: Path = CONTRACTS_ROOT) -> Path:
        """What the Scala service was captured doing: its newest `contracts/<name>/<date>/`.

        Raises:
            ContractsError: if there is none yet, or one lacks its provenance.
        """
        return latest_capture(root, self.name)


USER_PATH = re.compile(r"^/users/([^/?]+)$")


def user_lookup(path: str) -> bytes | None:
    """user-service's `GET /users/{id}` for an existing user (capture http/users-200.txt's
    shape); None for any other path."""
    match = USER_PATH.match(path)
    if match is None:
        return None
    user_id = match.group(1)
    return json.dumps(
        {
            "userId": user_id,
            "email": f"{user_id}@example.com",
            "createdAt": "2026-11-09T18:43:19.511602Z",
        },
        separators=(",", ":"),
    ).encode()


PROFILES = (
    # Its outbox reaches Kafka through Debezium (the CDC group's stack), not a client.
    # Called by notification-service (recipient lookup) and the consumer probe.
    ServiceProfile(name="user-service", stub=user_lookup),
    # application.conf: kafka.bootstrap-servers, user-client, order-client (ADR 0025).
    ServiceProfile(
        name="notification-service",
        kafka=True,
        topics=("user-events", "order-events", "payment-events", "fulfilment-events"),
        calls=("user-service", "order-service"),
    ),
)

KNOWN_SERVICES = tuple(known.name for known in PROFILES)
"""The services a run can judge, one named per run (no default: gluon TD-44)."""


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


def variable_prefix(service: str) -> str:
    """Its profile's prefix, else `notification-service` → `NOTIFICATION_SERVICE`; a
    service the harness only stubs has no profile and the derived prefix."""
    own = next((known.prefix for known in PROFILES if known.name == service), None)
    return own or service.removesuffix("-service").upper().replace("-", "_") + "_SERVICE"


def stub_answer(service: str) -> Answer:
    """How a stub for `service` answers: its profile's; a service the harness only stubs
    (no profile) finds nothing until a check scripts it."""
    return next((known.stub for known in PROFILES if known.name == service), no_answer)
