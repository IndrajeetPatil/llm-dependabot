"""Tests for config.yaml validation and loading."""

import datetime as dt
import json
from pathlib import Path
from typing import Any, cast

import pytest
import typer
import yaml
from pydantic import ValidationError

from llm_dependabot import config as config_module
from llm_dependabot.config import Agent, Config, is_weekend, load_config
from llm_dependabot.paths import ROOT

# YAML reads an unquoted 9:00 as the sexagesimal integer 540.
UNQUOTED_TIME: int = cast("int", yaml.safe_load("time: 9:00")["time"])


def validate(raw: dict[str, Any]) -> Config:
    """Validate a raw config as load_config does."""
    return Config.model_validate_json(json.dumps(raw))


def set_at(raw: dict[str, Any], path: tuple[str | int, ...], value: object) -> None:
    """Set the value at a path of keys and list indices in the raw config."""
    *parents, last = path
    node: Any = raw
    for key in parents:
        node = node[key]
    node[last] = value


def test_the_committed_config_is_valid() -> None:
    """The repository's own config.yaml validates."""
    config = Config.model_validate_json(
        config_module.yaml_to_json(ROOT / "config.yaml")
    )
    assert config.groups
    assert config.bundle_id.endswith(".llm-dependabot")


def test_the_bundle_id_names_the_app_and_its_agents(config: Config) -> None:
    """The prefix plus the tool's name identifies the app and prefixes labels."""
    assert config.bundle_id == "com.example.llm-dependabot"
    assert config.launchd_label("python") == "com.example.llm-dependabot.python"


def test_values_are_parsed(config: Config) -> None:
    """Times, defaults, and cadences are parsed."""
    assert config.groups[1].time == dt.time(9, 30)
    assert config.prompts[0].cadence == "weekly"
    assert config.skip_weekends


@pytest.mark.parametrize(
    ("path", "value", "match"),
    [
        pytest.param(("ownr",), "typo", "ownr", id="unknown key"),
        pytest.param(("groups", 0, "time"), UNQUOTED_TIME, "time", id="unquoted time"),
        pytest.param(("groups", 1, "name"), "python", "unique", id="duplicate group"),
        pytest.param(
            ("prompts", 1, "name"), "update-deps", "unique", id="duplicate prompt"
        ),
        pytest.param(("prompts", 0, "name"), "-x", "pattern", id="bad prompt name"),
        pytest.param(("label", "color"), "red", "pattern", id="bad label colour"),
        pytest.param(
            ("bundle_id_prefix",), "com example", "pattern", id="bad bundle prefix"
        ),
        pytest.param(("agent", "command"), [], "at least 1", id="empty command"),
        pytest.param(("agent_timeout_hours",), 0, "greater than 0", id="zero timeout"),
        pytest.param(
            ("groups", 0, "cadence"),
            {"no-such-prompt": "monthly"},
            "unknown prompts",
            id="override for an unknown prompt",
        ),
        pytest.param(
            ("groups", 0, "weekday"), "Saturday", "skip_weekends", id="weekend group"
        ),
    ],
)
def test_invalid_configuration_is_rejected(
    raw_config: dict[str, Any],
    path: tuple[str | int, ...],
    value: object,
    match: str,
) -> None:
    """Each kind of mistake fails validation with a message naming it."""
    set_at(raw_config, path, value)
    with pytest.raises(ValidationError, match=match):
        validate(raw_config)


@pytest.mark.parametrize(
    ("changes", "attribute", "expected"),
    [
        pytest.param(
            {("clone_root",): "~/clones"},
            "clone_root",
            Path.home() / "clones",
            id="clone root under home",
        ),
        pytest.param(
            {("groups", 0, "weekday"): "Saturday", ("skip_weekends",): False},
            "skip_weekends",
            False,
            id="weekend group without skip_weekends",
        ),
    ],
)
def test_valid_variations_are_accepted(
    raw_config: dict[str, Any],
    changes: dict[tuple[str | int, ...], object],
    attribute: str,
    expected: object,
) -> None:
    """Variations on the valid config load, with values normalised."""
    for path, value in changes.items():
        set_at(raw_config, path, value)
    assert getattr(validate(raw_config), attribute) == expected


@pytest.mark.parametrize(
    ("group", "cadence"), [("python", "weekly"), ("rest", "monthly")]
)
def test_a_group_overrides_a_prompt_cadence(
    config: Config, group: str, cadence: str
) -> None:
    """A group's cadence override replaces the prompt's own."""
    assert config.group(group).cadence_for(config.prompt("update-deps")) == cadence


@pytest.mark.parametrize("method", ["group", "prompt"])
def test_an_unknown_name_fails(config: Config, method: str) -> None:
    """Looking up an unknown group or prompt fails."""
    with pytest.raises(typer.Exit):
        getattr(config, method)("missing")


@pytest.mark.parametrize(
    ("command", "hours", "argv", "via_stdin"),
    [
        pytest.param(
            ["agent", "--hours", "{timeout_hours}h", "{prompt}"],
            1.5,
            ["agent", "--hours", "1.5h", "Do it {timeout_hours}"],
            False,
            id="placeholders filled",
        ),
        pytest.param(["agent", "-"], 4, ["agent", "-"], True, id="prompt on stdin"),
    ],
)
def test_agent_argv(
    command: list[str], hours: float, argv: list[str], *, via_stdin: bool
) -> None:
    """The prompt fills its placeholder argument, or goes to stdin without one."""
    agent = Agent(name="a", command=command)
    assert agent.argv("Do it {timeout_hours}", hours) == (argv, via_stdin)


@pytest.mark.parametrize(
    ("today", "skip", "expected"),
    [
        pytest.param(dt.date(2026, 11, 28), True, True, id="Saturday"),
        pytest.param(dt.date(2026, 11, 28), False, False, id="Saturday, not skipped"),
        pytest.param(dt.date(2026, 11, 26), True, False, id="Thursday"),
    ],
)
def test_is_weekend(
    config: Config,
    monkeypatch: pytest.MonkeyPatch,
    today: dt.date,
    *,
    skip: bool,
    expected: bool,
) -> None:
    """Weekends count only when skip_weekends is on."""
    monkeypatch.setattr(config_module, "local_today", lambda: today)
    config.skip_weekends = skip
    assert is_weekend(config) is expected


@pytest.fixture
def config_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Point load_config at a config.yaml and private.yaml in a temporary directory."""
    config_file = tmp_path / "config.yaml"
    private_file = tmp_path / "private.yaml"
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)
    monkeypatch.setattr(config_module, "PRIVATE_FILE", private_file)
    return config_file, private_file


@pytest.mark.parametrize(
    ("private", "expected"),
    [
        pytest.param(None, frozenset(), id="no private.yaml"),
        pytest.param("repos: [secret]\n", frozenset({"secret"}), id="one repository"),
        pytest.param("{}\n", frozenset(), id="empty private.yaml"),
    ],
)
def test_load_config_adds_the_private_repositories(
    config_files: tuple[Path, Path],
    raw_config: dict[str, Any],
    private: str | None,
    expected: frozenset[str],
) -> None:
    """load_config reads the private repositories from private.yaml."""
    config_file, private_file = config_files
    config_file.write_text(yaml.safe_dump(raw_config))
    if private is not None:
        private_file.write_text(private)
    assert load_config().private_repos == expected


@pytest.mark.parametrize(
    ("config_text", "private"),
    [
        pytest.param("owner: octo\n", None, id="incomplete config.yaml"),
        pytest.param(None, "repos: secret\n", id="private repos not a list"),
    ],
)
def test_load_config_reports_invalid_configuration(
    config_files: tuple[Path, Path],
    raw_config: dict[str, Any],
    config_text: str | None,
    private: str | None,
) -> None:
    """load_config fails on an invalid config.yaml or private.yaml."""
    config_file, private_file = config_files
    config_file.write_text(config_text or yaml.safe_dump(raw_config))
    if private is not None:
        private_file.write_text(private)
    with pytest.raises(typer.Exit):
        load_config()
