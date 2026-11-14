# SPDX-License-Identifier: MIT

"""The Kafka broker's configuration (RUST-1.8; gluon TD-45), without starting Java."""

from pathlib import Path

import pytest

from gluon_contract.kafka import CLUSTER_ID, Jars, broker_properties, properties_text
from gluon_contract.supervisor import StackError


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


def test_properties_text_is_one_key_value_line_each() -> None:
    """In the mapping's order."""
    assert properties_text({"b": "2", "a": "1"}) == "b=2\na=1\n"


def test_missing_jars_are_named_with_how_to_install_them(tmp_path: Path) -> None:
    """Before anything is written or started."""
    (tmp_path / "home" / "kafka").mkdir(parents=True)
    jars = Jars(tmp_path / "home", tmp_path / "work", "java")
    with pytest.raises(StackError, match=r"missing connect, plugins\): run gluon"):
        jars.prepare(("kafka", "connect", "plugins"))
    assert not (tmp_path / "work").exists()


def test_a_java_command_line_uses_one_jar_set_and_the_logging_config(tmp_path: Path) -> None:
    """Heap, log4j config from the work directory, the jar set's classpath, then the main."""
    (tmp_path / "home" / "kafka").mkdir(parents=True)
    jars = Jars(tmp_path / "home", tmp_path / "work", "/jdk/bin/java")
    jars.prepare(("kafka",))
    assert (tmp_path / "work" / "log4j.properties").is_file()
    assert jars.argv("kafka", "256m", "kafka.Kafka", "server.properties") == [
        "/jdk/bin/java",
        "-Xms64m",
        "-Xmx256m",
        f"-Dlog4j.configuration=file:{tmp_path / 'work' / 'log4j.properties'}",
        "-cp",
        str(tmp_path / "home" / "kafka" / "*"),
        "kafka.Kafka",
        "server.properties",
    ]
