# SPDX-License-Identifier: MIT

"""The Kafka broker's configuration (RUST-1.8; gluon TD-45), without starting Java."""

from pathlib import Path

from gluon_contract.kafka import CLUSTER_ID, broker_properties


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
