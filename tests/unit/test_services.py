# SPDX-License-Identifier: MIT

"""What the harness starts for each service besides Postgres and the OTLP stub (RPN-3 FR2).

Sources: each service's `application.conf` (`${?VAR}` overrides) and gluon
`environments/local/<service>.values.yaml`; for notification-service's topics, the
capture's `CAPTURE.sh`.
"""

import json
from pathlib import Path

import pytest

from gluon_contract import services
from gluon_contract.config import load_config
from gluon_contract.env_contract import Endpoints, service_env
from gluon_contract.notification_scenarios import TOPICS
from gluon_contract.services import (
    KNOWN_SERVICES,
    PROFILES,
    ServiceProfile,
    UnknownServiceError,
    profile,
    stub_answer,
    variable_prefix,
)


def test_user_service_needs_nothing_beyond_postgres_and_otlp() -> None:
    """user-service reads no broker and calls no service (its outbox reaches Kafka by CDC)."""
    user = profile("user-service")
    assert (user.kafka, user.topics, user.calls) == (False, (), ())
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
    """In the order the ports began; a run names one (there is no default)."""
    assert KNOWN_SERVICES == ("user-service", "notification-service")


def test_a_service_without_a_profile_is_an_error_naming_the_known_ones() -> None:
    """order-service is a gluon service, but the harness can't start it yet."""
    with pytest.raises(UnknownServiceError, match="order-service") as raised:
        profile("order-service")
    assert "user-service, notification-service" in str(raised.value)


def test_topics_need_a_broker() -> None:
    """Every profile that consumes topics gets a broker to create them on."""
    assert all(known.kafka for known in PROFILES if known.topics)


def test_a_stub_for_user_service_answers_a_user_lookup() -> None:
    """Its profile's stub answer: `GET /users/{id}` as the capture's users-200 shape."""
    answer = stub_answer("user-service")
    body = answer("/users/abc")
    assert body is not None
    assert json.loads(body) == {
        "userId": "abc",
        "email": "abc@example.com",
        "createdAt": "2026-11-09T18:43:19.511602Z",
    }
    assert answer("/users/abc/orders") is None


def test_a_stub_for_a_service_without_answers_finds_nothing() -> None:
    """order-service has no profile (the harness only stubs it): its stub finds no order."""
    assert stub_answer("order-service")("/orders/1") is None


def test_a_new_service_is_one_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Adding a service (cart-service, say) is its profile plus its checks (gluon TD-44):
    the harness finds its capture, names its variables, configures a run for it, and
    stubs it for a caller, with nothing else edited."""
    cart = ServiceProfile(name="cart-service", calls=("user-service",), stub=lambda _: b"{}")
    monkeypatch.setattr(services, "PROFILES", (*services.PROFILES, cart))
    capture = tmp_path / "cart-service" / "20261120"
    capture.mkdir(parents=True)
    (capture / "PROVENANCE.md").write_text("laptop\n", encoding="utf-8")

    assert profile("cart-service").capture(tmp_path) == capture
    assert variable_prefix("cart-service") == "CART_SERVICE"
    endpoints = Endpoints(
        http_port=1,
        metrics_port=2,
        postgres_host="127.0.0.1",
        postgres_port=3,
        otlp_endpoint="http://127.0.0.1:4",
        service_urls={"user-service": "http://stub"},
    )
    env = service_env("cart-service", endpoints, base_env={})
    assert (env["CART_SERVICE_PORT"], env["POSTGRES_DB"], env["USER_SERVICE_URL"]) == (
        "1",
        "cart",
        "http://stub",
    )
    assert stub_answer("cart-service")("/carts/1") == b"{}"
    pg_bin = tmp_path / "pg"
    pg_bin.mkdir()
    for tool in ("initdb", "pg_ctl", "createdb"):
        (pg_bin / tool).write_text("#!/bin/sh\n", encoding="utf-8")
        (pg_bin / tool).chmod(0o755)
    config = load_config(
        {"CONTRACT_TARGET_CMD": "cart", "CONTRACT_SERVICE": "cart-service"},
        cwd=tmp_path,
        which=lambda name: str(pg_bin / name),
    )
    assert config.service == "cart-service"
