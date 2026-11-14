# SPDX-License-Identifier: MIT

"""HarnessConfig: how a run is configured (RUST-1.2 spec FR1)."""

from pathlib import Path

import pytest

from gluon_contract.cdc import cdc_home
from gluon_contract.config import ConfigError, HarnessConfig, find_pg_bin, load_config

PG_TOOLS = ("initdb", "pg_ctl", "createdb")


def make_pg_bin(directory: Path, tools: tuple[str, ...] = PG_TOOLS) -> Path:
    """A directory holding (empty, executable) stand-ins for the Postgres binaries."""
    directory.mkdir(parents=True, exist_ok=True)
    for tool in tools:
        path = directory / tool
        path.write_text("#!/bin/sh\n", encoding="utf-8")
        path.chmod(0o755)
    return directory


def make_cdc_home(directory: Path) -> Path:
    """A CDC home with the broker's jar directory (its contents aren't looked at)."""
    (directory / "kafka").mkdir(parents=True)
    return directory


def no_executables(_name: str) -> str | None:
    """A PATH lookup that finds nothing."""
    return None


def test_defaults_apply_when_only_the_target_command_is_given(tmp_path: Path) -> None:
    """Everything but the target command has a default."""
    pg_bin = make_pg_bin(tmp_path / "pg")
    config = load_config(
        {"CONTRACT_TARGET_CMD": "./target/debug/user-service", "CONTRACT_PG_BIN": str(pg_bin)},
        cwd=tmp_path,
        which=no_executables,
    )
    assert config == HarnessConfig(
        target_argv=("./target/debug/user-service",),
        target_cwd=tmp_path,
        target_name="user-service",
        service="user-service",
        pg_bin=pg_bin,
        readiness_path="/health/ready",
        readiness_deadline_s=60.0,
        keep_artifacts=False,
    )


def test_every_setting_can_be_overridden(tmp_path: Path) -> None:
    """Each CONTRACT_* variable overrides its default."""
    pg_bin = make_pg_bin(tmp_path / "pg")
    work = tmp_path / "work"
    work.mkdir()
    cdc = make_cdc_home(tmp_path / "cdc")
    config = load_config(
        {
            "CONTRACT_TARGET_CMD": "java -jar 'user service.jar' --flag",
            "CONTRACT_TARGET_CWD": str(work),
            "CONTRACT_TARGET_NAME": "scala",
            "CONTRACT_SERVICE": "notification-service",
            "CONTRACT_CDC_HOME": str(cdc),
            "CONTRACT_PG_BIN": str(pg_bin),
            "CONTRACT_READINESS_PATH": "/health",
            "CONTRACT_READINESS_DEADLINE": "12.5",
            "CONTRACT_KEEP_ARTIFACTS": "true",
        },
        cwd=tmp_path,
        which=no_executables,
    )
    assert config.target_argv == ("java", "-jar", "user service.jar", "--flag")
    assert config.target_cwd == work
    assert config.target_name == "scala"
    assert config.service == "notification-service"
    assert config.kafka_home == cdc
    assert config.readiness_path == "/health"
    assert config.readiness_deadline_s == 12.5
    assert config.keep_artifacts is True


def test_a_service_without_a_profile_is_a_problem_naming_the_known_ones(tmp_path: Path) -> None:
    """A well-formed name the harness can't start is reported with the other problems."""
    with pytest.raises(ConfigError) as raised:
        load_config({"CONTRACT_SERVICE": "order-service"}, cwd=tmp_path, which=no_executables)
    problems = raised.value.problems
    assert any(
        "CONTRACT_SERVICE" in p and "'order-service'" in p and "notification-service" in p
        for p in problems
    ), problems
    assert any("CONTRACT_TARGET_CMD" in p for p in problems)


def test_user_service_needs_no_kafka_jars(tmp_path: Path) -> None:
    """No broker for user-service: a missing CDC home is no problem, and none is kept."""
    pg_bin = make_pg_bin(tmp_path / "pg")
    config = load_config(
        {
            "CONTRACT_TARGET_CMD": "svc",
            "CONTRACT_PG_BIN": str(pg_bin),
            "CONTRACT_CDC_HOME": str(tmp_path / "nowhere"),
        },
        cwd=tmp_path,
        which=no_executables,
    )
    assert config.kafka_home is None


def test_a_service_that_needs_a_broker_needs_the_kafka_jars(tmp_path: Path) -> None:
    """notification-service reads Kafka; without the broker's jars it can't be started."""
    pg_bin = make_pg_bin(tmp_path / "pg")
    with pytest.raises(ConfigError) as raised:
        load_config(
            {
                "CONTRACT_TARGET_CMD": "svc",
                "CONTRACT_SERVICE": "notification-service",
                "CONTRACT_PG_BIN": str(pg_bin),
                "CONTRACT_CDC_HOME": str(tmp_path / "nowhere"),
            },
            cwd=tmp_path,
            which=no_executables,
        )
    (problem,) = raised.value.problems
    assert "notification-service needs a Kafka broker" in problem
    assert str(tmp_path / "nowhere" / "kafka") in problem
    assert "bin/sandbox-setup --only cdc" in problem


def test_the_kafka_jars_default_to_where_sandbox_setup_puts_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without CONTRACT_CDC_HOME, the CDC group's default home (cdc.cdc_home) is used."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    pg_bin = make_pg_bin(tmp_path / "pg")
    raw = {
        "CONTRACT_TARGET_CMD": "svc",
        "CONTRACT_SERVICE": "notification-service",
        "CONTRACT_PG_BIN": str(pg_bin),
    }
    default = make_cdc_home(cdc_home(raw))
    assert default.is_relative_to(tmp_path / "home" / ".local")
    assert load_config(raw, cwd=tmp_path, which=no_executables).kafka_home == default


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1", True), ("yes", True), ("TRUE", True), ("0", False), ("no", False), ("", False)],
)
def test_keep_artifacts_accepts_common_spellings(tmp_path: Path, raw: str, expected: bool) -> None:
    """Booleans accept 1/0, yes/no, true/false, any case; empty means false."""
    pg_bin = make_pg_bin(tmp_path / "pg")
    config = load_config(
        {
            "CONTRACT_TARGET_CMD": "svc",
            "CONTRACT_PG_BIN": str(pg_bin),
            "CONTRACT_KEEP_ARTIFACTS": raw,
        },
        cwd=tmp_path,
        which=no_executables,
    )
    assert config.keep_artifacts is expected


def test_postgres_binaries_are_found_through_pg_ctl_on_the_path(tmp_path: Path) -> None:
    """Without CONTRACT_PG_BIN, the directory of pg_ctl's real file is used, symlinks resolved."""
    real = make_pg_bin(tmp_path / "lib" / "postgresql" / "16" / "bin")
    links = tmp_path / "usr-local-bin"
    links.mkdir()
    (links / "pg_ctl").symlink_to(real / "pg_ctl")

    def which(name: str) -> str | None:
        return str(links / "pg_ctl") if name == "pg_ctl" else None

    config = load_config({"CONTRACT_TARGET_CMD": "svc"}, cwd=tmp_path, which=which)
    assert config.pg_bin == real


def test_every_invalid_value_is_reported_together(tmp_path: Path) -> None:
    """One ConfigError lists every problem, so a run needs only one fix-up round."""
    incomplete_pg = make_pg_bin(tmp_path / "pg", tools=("pg_ctl",))
    with pytest.raises(ConfigError) as raised:
        load_config(
            {
                "CONTRACT_TARGET_CMD": "  ",
                "CONTRACT_TARGET_CWD": str(tmp_path / "missing"),
                "CONTRACT_SERVICE": "Users",
                "CONTRACT_PG_BIN": str(incomplete_pg),
                "CONTRACT_READINESS_PATH": "health",
                "CONTRACT_READINESS_DEADLINE": "-1",
                "CONTRACT_KEEP_ARTIFACTS": "maybe",
            },
            cwd=tmp_path,
            which=no_executables,
        )
    problems = raised.value.problems
    assert len(problems) == 7
    message = str(raised.value)
    for fragment in (
        "CONTRACT_TARGET_CMD",
        "CONTRACT_TARGET_CWD",
        "CONTRACT_SERVICE",
        "CONTRACT_PG_BIN",
        "initdb",
        "createdb",
        "CONTRACT_READINESS_PATH",
        "CONTRACT_READINESS_DEADLINE",
        "CONTRACT_KEEP_ARTIFACTS",
    ):
        assert fragment in message


def test_unbalanced_quotes_in_the_target_command_are_a_problem(tmp_path: Path) -> None:
    """The target command is split like a shell would; a split error is reported, not raised raw."""
    pg_bin = make_pg_bin(tmp_path / "pg")
    with pytest.raises(ConfigError, match="CONTRACT_TARGET_CMD"):
        load_config(
            {"CONTRACT_TARGET_CMD": "java -jar 'unterminated", "CONTRACT_PG_BIN": str(pg_bin)},
            cwd=tmp_path,
            which=no_executables,
        )


def test_missing_target_command_and_postgres_are_reported(tmp_path: Path) -> None:
    """No target command, and no pg_ctl anywhere: both problems, with what to set."""
    with pytest.raises(ConfigError) as raised:
        load_config({}, cwd=tmp_path, which=no_executables)
    message = str(raised.value)
    assert "CONTRACT_TARGET_CMD" in message
    assert "CONTRACT_PG_BIN" in message
    assert "pg_ctl" in message


def test_a_deadline_that_is_not_a_number_is_a_problem(tmp_path: Path) -> None:
    """CONTRACT_READINESS_DEADLINE is seconds; words are reported, not raised raw."""
    pg_bin = make_pg_bin(tmp_path / "pg")
    with pytest.raises(ConfigError, match="CONTRACT_READINESS_DEADLINE must be a number"):
        load_config(
            {
                "CONTRACT_TARGET_CMD": "svc",
                "CONTRACT_PG_BIN": str(pg_bin),
                "CONTRACT_READINESS_DEADLINE": "soon",
            },
            cwd=tmp_path,
            which=no_executables,
        )


def test_find_pg_bin_resolves_the_same_way_as_the_config(tmp_path: Path) -> None:
    """`find_pg_bin` gives callers outside a run (tests, tools) the same lookup as load_config."""
    real = make_pg_bin(tmp_path / "pg")
    assert find_pg_bin(str(real), which=no_executables) == real

    def which(name: str) -> str | None:
        return str(real / "pg_ctl") if name == "pg_ctl" else None

    assert find_pg_bin(None, which=which) == real
    with pytest.raises(ConfigError, match="CONTRACT_PG_BIN"):
        find_pg_bin(None, which=no_executables)
