# SPDX-License-Identifier: MIT

"""What the harness starts for each service besides Postgres and the OTLP stub (RPN-3 FR2).

Sources: each service's `application.conf` (`${?VAR}` overrides) and gluon
`environments/local/<service>.values.yaml`; for notification-service's topics, the
capture's `CAPTURE.sh`.
"""

import pytest

from gluon_contract.notification_scenarios import TOPICS
from gluon_contract.services import (
    KNOWN_SERVICES,
    PROFILES,
    ServiceProfile,
    UnknownServiceError,
    profile,
)


def test_user_service_needs_nothing_beyond_postgres_and_otlp() -> None:
    """user-service reads no broker and calls no service (its outbox reaches Kafka by CDC)."""
    assert profile("user-service") == ServiceProfile(name="user-service")
    assert profile("user-service").kafka is False


def test_notification_service_needs_a_broker_with_its_four_input_topics() -> None:
    """KAFKA_BOOTSTRAP_SERVERS; the topics CAPTURE.sh creates before the service starts."""
    notification = profile("notification-service")
    assert notification.kafka is True
    assert notification.topics == (
        "user-events",
        "order-events",
        "payment-events",
        "fulfilment-events",
    )
    assert notification.topics == TOPICS


def test_notification_service_calls_user_service_and_order_service() -> None:
    """USER_SERVICE_URL and ORDER_SERVICE_URL (recipient resolution, ADR 0025)."""
    assert profile("notification-service").calls == ("user-service", "order-service")


def test_the_known_services_are_the_profiled_ones() -> None:
    """user-service first: it is the default a run judges."""
    assert KNOWN_SERVICES == ("user-service", "notification-service")


def test_a_service_without_a_profile_is_an_error_naming_the_known_ones() -> None:
    """order-service is a gluon service, but the harness can't start it yet."""
    with pytest.raises(UnknownServiceError, match="order-service") as raised:
        profile("order-service")
    assert "user-service, notification-service" in str(raised.value)


def test_topics_need_a_broker() -> None:
    """Every profile that consumes topics gets a broker to create them on."""
    assert all(known.kafka for known in PROFILES if known.topics)
