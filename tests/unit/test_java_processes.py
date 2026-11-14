# SPDX-License-Identifier: MIT

"""Java processes for the local stacks (gluon TD-45), without starting Java."""

from pathlib import Path

import pytest

from gluon_contract.java_processes import (
    JavaProcesses,
    StackError,
    cdc_home,
    properties_text,
)


def test_the_home_defaults_to_what_sandbox_setup_installs(tmp_path: Path) -> None:
    """CONTRACT_CDC_HOME, else ~/.local/cdc-kafka-3.8.0_debezium-3.0.0.Final."""
    assert cdc_home({}, home=tmp_path) == tmp_path / ".local/cdc-kafka-3.8.0_debezium-3.0.0.Final"
    assert cdc_home({"CONTRACT_CDC_HOME": "/opt/cdc"}, home=tmp_path) == Path("/opt/cdc")


def test_properties_text_is_one_key_value_line_each() -> None:
    """In the mapping's order."""
    assert properties_text({"b": "2", "a": "1"}) == "b=2\na=1\n"


def test_missing_jars_are_named_with_how_to_install_them(tmp_path: Path) -> None:
    """Before anything is written or started."""
    (tmp_path / "home" / "kafka").mkdir(parents=True)
    processes = JavaProcesses(tmp_path / "home", tmp_path / "work", "java")
    with pytest.raises(StackError, match=r"missing connect, plugins\): run gluon"):
        processes.prepare(("kafka", "connect", "plugins"))
    assert not (tmp_path / "work").exists()


def test_a_java_command_line_uses_one_jar_set_and_the_logging_config(tmp_path: Path) -> None:
    """Heap, log4j config from the work directory, the jar set's classpath, then the main."""
    (tmp_path / "home" / "kafka").mkdir(parents=True)
    processes = JavaProcesses(tmp_path / "home", tmp_path / "work", "/jdk/bin/java")
    processes.prepare(("kafka",))
    assert (tmp_path / "work" / "log4j.properties").is_file()
    assert processes.argv("kafka", "256m", "kafka.Kafka", "server.properties") == [
        "/jdk/bin/java",
        "-Xms64m",
        "-Xmx256m",
        f"-Dlog4j.configuration=file:{tmp_path / 'work' / 'log4j.properties'}",
        "-cp",
        str(tmp_path / "home" / "kafka" / "*"),
        "kafka.Kafka",
        "server.properties",
    ]


def test_a_log_reads_as_empty_until_written_and_its_tail_is_the_last_lines(
    tmp_path: Path,
) -> None:
    """`text` is '' and `tail` says so before the process writes anything."""
    processes = JavaProcesses(tmp_path, tmp_path, "java")
    assert processes.text("x.log") == ""
    assert processes.tail("x.log") == "(no log)"
    (tmp_path / "x.log").write_text("".join(f"line {n}\n" for n in range(30)))
    assert processes.tail("x.log").splitlines() == [f"line {n}" for n in range(10, 30)]
