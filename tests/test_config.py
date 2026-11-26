"""Tests for config.yaml validation and loading."""

import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest
import typer
import yaml
from pydantic import ValidationError

from llm_dependabot import config as config_module
from llm_dependabot.config import Agent, Config, is_weekend, load_config
from llm_dependabot.paths import ROOT


def validate(raw: dict[str, Any]) -> Config:
    """Validate a raw config as load_config does."""
    return Config.model_validate_json(json.dumps(raw))


def test_the_committed_config_is_valid() -> None:
    """The repository's own config.yaml validates."""
    config = Config.model_validate_json(
        config_module.yaml_to_json(ROOT / "config.yaml")
    )
    assert config.groups
    assert all(group.label.endswith(f".{group.name}") for group in config.groups)


def test_values_are_parsed(config: Config) -> None:
    """Times, defaults, and cadences are parsed."""
    assert config.groups[1].time == dt.time(9, 30)
    assert config.prompts[0].cadence == "weekly"
    assert config.skip_weekends


def test_clone_root_expands_the_home_directory(raw_config: dict[str, Any]) -> None:
    """A clone_root under ~ is expanded."""
    raw_config["clone_root"] = "~/clones"
    assert validate(raw_config).clone_root == Path.home() / "clones"


def test_unknown_keys_are_rejected(raw_config: dict[str, Any]) -> None:
    """A misspelt key fails validation."""
    raw_config["ownr"] = "typo"
    with pytest.raises(ValidationError, match="ownr"):
        validate(raw_config)


def test_an_unquoted_time_is_rejected(raw_config: dict[str, Any]) -> None:
    # YAML reads an unquoted 9:00 as the sexagesimal integer 540.
    """A time YAML read as a number fails validation."""
    raw_config["groups"][0]["time"] = yaml.safe_load("time: 9:00")["time"]
    with pytest.raises(ValidationError):
        validate(raw_config)


@pytest.mark.parametrize("kind", ["groups", "prompts"])
def test_names_must_be_unique(raw_config: dict[str, Any], kind: str) -> None:
    """Duplicate group or prompt names fail validation."""
    raw_config[kind].append(raw_config[kind][0])
    with pytest.raises(ValidationError, match="names must be unique"):
        validate(raw_config)


def test_a_cadence_override_must_name_a_known_prompt(
    raw_config: dict[str, Any],
) -> None:
    """A cadence override for an unknown prompt fails validation."""
    raw_config["groups"][0]["cadence"] = {"no-such-prompt": "monthly"}
    with pytest.raises(ValidationError, match="unknown prompts"):
        validate(raw_config)


def test_a_weekend_group_needs_skip_weekends_off(raw_config: dict[str, Any]) -> None:
    """A group on a weekend day is valid only without skip_weekends."""
    raw_config["groups"][0]["weekday"] = "Saturday"
    with pytest.raises(ValidationError, match="skip_weekends"):
        validate(raw_config)
    raw_config["skip_weekends"] = False
    assert validate(raw_config).groups[0].weekday == "Saturday"


def test_a_group_overrides_a_prompt_cadence(config: Config) -> None:
    """A group's cadence override replaces the prompt's own."""
    update_deps = config.prompt("update-deps")
    assert config.group("python").cadence_for(update_deps) == "weekly"
    assert config.group("rest").cadence_for(update_deps) == "monthly"


@pytest.mark.parametrize("method", ["group", "prompt"])
def test_an_unknown_name_fails(config: Config, method: str) -> None:
    """Looking up an unknown group or prompt fails."""
    with pytest.raises(typer.Exit):
        getattr(config, method)("missing")


def test_the_prompt_replaces_its_placeholder_argument() -> None:
    """The prompt and timeout fill their placeholders."""
    agent = Agent(
        name="a", command=["agent", "--hours", "{timeout_hours}h", "{prompt}"]
    )
    argv, via_stdin = agent.argv("Do it {timeout_hours}", 1.5)
    assert argv == ["agent", "--hours", "1.5h", "Do it {timeout_hours}"]
    assert not via_stdin


def test_without_a_placeholder_the_prompt_goes_to_stdin() -> None:
    """Without a prompt placeholder, the prompt is piped to stdin."""
    argv, via_stdin = Agent(name="a", command=["agent", "-"]).argv("text", 4)
    assert argv == ["agent", "-"]
    assert via_stdin


@pytest.mark.parametrize(
    ("today", "skip", "expected"),
    [
        (dt.date(2026, 11, 28), True, True),  # a Saturday
        (dt.date(2026, 11, 28), False, False),
        (dt.date(2026, 11, 26), True, False),  # a Thursday
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


def test_load_config_adds_the_private_repositories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raw_config: dict[str, Any]
) -> None:
    """load_config reads the private repositories from private.yaml."""
    config_file = tmp_path / "config.yaml"
    private_file = tmp_path / "private.yaml"
    config_file.write_text(yaml.safe_dump(raw_config))
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)
    monkeypatch.setattr(config_module, "PRIVATE_FILE", private_file)
    assert load_config().private_repos == frozenset()

    private_file.write_text("repos: [secret]\n")
    assert load_config().private_repos == {"secret"}


def test_load_config_reports_invalid_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """load_config fails on an invalid config.yaml."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("owner: octo\n")
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)
    with pytest.raises(typer.Exit):
        load_config()
