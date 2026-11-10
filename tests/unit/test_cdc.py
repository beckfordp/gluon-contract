# SPDX-License-Identifier: MIT

"""The sandbox CDC stack's configuration (RUST-1.8), without starting Java."""

from pathlib import Path

import pytest

from gluon_contract.cdc import (
    CLUSTER_ID,
    CdcError,
    CdcStack,
    broker_properties,
    cdc_home,
    connector_properties,
    worker_properties,
)
from gluon_contract.env_contract import postgres_login
from gluon_contract.postgres import PostgresEndpoint
from gluon_contract.routing import load_connector

ENDPOINT = PostgresEndpoint("127.0.0.1", 55432, postgres_login("user-service"))


def properties(text: str) -> dict[str, str]:
    """A .properties text as a dict (no continuation lines in ours)."""
    pairs = (line.split("=", 1) for line in text.splitlines() if line and not line.startswith("#"))
    return {key: value for key, value in pairs}


def test_the_broker_is_a_single_kraft_node_on_loopback(tmp_path: Path) -> None:
    """Broker and controller in one process, replication factors 1, gluon-local's cluster id."""
    config = properties(broker_properties(tmp_path / "data", 59092, 59093))
    assert config["process.roles"] == "broker,controller"
    assert config["listeners"] == "PLAINTEXT://127.0.0.1:59092,CONTROLLER://127.0.0.1:59093"
    assert config["advertised.listeners"] == "PLAINTEXT://127.0.0.1:59092"
    assert config["controller.quorum.voters"] == "1@127.0.0.1:59093"
    assert config["log.dirs"] == str(tmp_path / "data")
    assert config["offsets.topic.replication.factor"] == "1"
    assert CLUSTER_ID == "MkU3OEVBNTcwNTJENDM2Qk"


def test_the_worker_passes_keys_and_values_through_as_strings(tmp_path: Path) -> None:
    """StringConverter for both, as gluon-local's Connect (kafka-connect.yaml)."""
    config = properties(worker_properties(tmp_path, "127.0.0.1:59092", 58083, tmp_path / "plugins"))
    assert config["bootstrap.servers"] == "127.0.0.1:59092"
    assert config["key.converter"] == "org.apache.kafka.connect.storage.StringConverter"
    assert config["value.converter"] == "org.apache.kafka.connect.storage.StringConverter"
    assert config["plugin.path"] == str(tmp_path / "plugins")
    assert config["listeners"] == "http://127.0.0.1:58083"


def test_the_connector_is_gluons_with_only_the_database_address_and_login_replaced() -> None:
    """Everything else, the routing above all, is exactly the registered config."""
    registered = load_connector("user-outbox-connector.json")
    config = properties(connector_properties("user-outbox-connector", registered, ENDPOINT))
    assert config.pop("name") == "user-outbox-connector"
    replaced = {
        "database.hostname": "127.0.0.1",
        "database.port": "55432",
        "database.dbname": "user",
        "database.user": "user",
        "database.password": "user",
    }
    assert {key: config[key] for key in replaced} == replaced
    assert {k: v for k, v in config.items() if k not in replaced} == {
        k: v for k, v in registered.items() if k not in replaced
    }


def test_the_home_defaults_to_what_sandbox_setup_installs(tmp_path: Path) -> None:
    """CONTRACT_CDC_HOME, else ~/.local/cdc-kafka-3.8.0_debezium-3.0.0.Final."""
    assert cdc_home({}, home=tmp_path) == tmp_path / ".local/cdc-kafka-3.8.0_debezium-3.0.0.Final"
    assert cdc_home({"CONTRACT_CDC_HOME": "/opt/cdc"}, home=tmp_path) == Path("/opt/cdc")


def test_missing_jars_are_reported_before_anything_starts(tmp_path: Path) -> None:
    """Names the directory and how to fill it."""
    with (
        pytest.raises(CdcError, match="sandbox-setup --only cdc"),
        CdcStack(tmp_path / "nowhere", tmp_path / "work", ENDPOINT),
    ):
        pass
