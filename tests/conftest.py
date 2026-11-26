"""Fixtures shared by every test: an isolated home, a valid config, fake commands."""

import json
import os
import sys
from typing import TYPE_CHECKING, Any

import pytest

import llm_dependabot.cli  # ruff: ignore[unused-import] (imports every module, so home can patch them)
from llm_dependabot.config import Config
from llm_dependabot.github import Repo

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point every per-user location at a temporary directory.

    pyproject.toml lists this fixture in usefixtures, so every test uses it and
    none can touch the real home directory.

    Modules import the constants from llm_dependabot.paths by name, so each
    module's own copy is patched.
    """
    home = tmp_path / "home"
    state_dir = home / "Library/Application Support/llm-dependabot"
    app_bundle = state_dir / "LLM Dependabot.app"
    locations = {
        "LAUNCH_AGENTS": home / "Library/LaunchAgents",
        "LOG_DIR": home / "Library/Logs/llm-dependabot",
        "STATE_DIR": state_dir,
        "STATE_FILE": state_dir / "state.json",
        "LOCK_FILE": state_dir / "lock",
        "WORKTREE_ROOT": home / "Library/Caches/llm-dependabot/worktrees",
        "APP_BUNDLE": app_bundle,
        "LAUNCHER": app_bundle / "Contents/MacOS/llm-dependabot",
        "DASHBOARD_FILE": tmp_path / "dashboard.html",
        "CONFIG_FILE": tmp_path / "config.yaml",
        "PRIVATE_FILE": tmp_path / "private.yaml",
    }
    for name, module in list(sys.modules.items()):
        if name == "llm_dependabot" or name.startswith("llm_dependabot."):
            for attribute, value in locations.items():
                if hasattr(module, attribute):
                    monkeypatch.setattr(module, attribute, value)
    return home


@pytest.fixture
def raw_config(tmp_path: Path) -> dict[str, Any]:
    """A valid config.yaml, as the dictionary YAML would load it."""
    return {
        "owner": "octo",
        "prompts": [
            {"name": "update-deps", "path": ".github/prompts/update-deps.md"},
            {
                "name": "simplify-codebase",
                "path": ".github/prompts/simplify-codebase.md",
                "cadence": "monthly",
            },
        ],
        "clone_root": str(tmp_path / "clones"),
        "agent": {
            "name": "Test agent",
            "command": ["agent", "--hours", "{timeout_hours}h", "-p", "{prompt}"],
        },
        "agent_timeout_hours": 4,
        "cleanup_interval_hours": 3,
        "label": {"name": "llm-dependabot", "color": "5fbfae"},
        "groups": [
            {
                "name": "python",
                "languages": ["Python"],
                "weekday": "Tuesday",
                "time": "11:00",
            },
            {
                "name": "rest",
                "languages": ["*"],
                "weekday": "Wednesday",
                "time": "09:30",
                "cadence": {"update-deps": "monthly"},
            },
        ],
    }


@pytest.fixture
def config(raw_config: dict[str, Any]) -> Config:
    """The raw config, validated as load_config validates it."""
    return Config.model_validate_json(json.dumps(raw_config))


@pytest.fixture
def make_repo() -> Callable[..., Repo]:
    """A factory for repositories owned by octo."""

    def make(name: str = "project", *prompts: str) -> Repo:
        """A repository carrying the named prompts."""
        return Repo(owner="octo", name=name, default_branch="main", prompts=prompts)

    return make


# Stands in for an external command: logs its arguments, then answers with the
# first matching rule in rules.json, using up rules that have a limited count.
FAKE_COMMAND = """\
import json, os, sys, time
state = os.environ["FAKE_COMMANDS"]
name, args = os.path.basename(sys.argv[0]), sys.argv[1:]
with open(os.path.join(state, "calls.jsonl"), "a") as calls:
    calls.write(json.dumps([name, *args]) + "\\n")
rules_path = os.path.join(state, "rules.json")
with open(rules_path) as file:
    rules = json.load(file)
line = " ".join(args)
for rule in rules:
    if rule["name"] == name and rule["match"] in line and rule["times"] != 0:
        rule["times"] -= 1
        with open(rules_path, "w") as file:
            json.dump(rules, file)
        sys.stdout.write(rule["stdout"])
        time.sleep(rule["sleep"])
        sys.exit(rule["code"])
"""


class FakeCommands:
    """Fake executables first on PATH, scripted per test and recording each call.

    The code under test runs them through its real subprocess calls, so the
    shell helpers are exercised too. Commands not installed stay missing.
    """

    def __init__(self, root: Path) -> None:
        """Keep the scripts in root/bin and their state in root."""
        self.root: Path = root
        self.bin: Path = root / "bin"
        self.bin.mkdir(parents=True)
        self.rules: list[dict[str, Any]] = []
        self.save()

    def save(self) -> None:
        """Write the rules where the fake commands read them."""
        (self.root / "rules.json").write_text(json.dumps(self.rules))

    def install(self, *names: str) -> None:
        """Put fake commands with these names on PATH; they succeed silently."""
        for name in names:
            script = self.bin / name
            script.write_text(f"#!{sys.executable} -I\n{FAKE_COMMAND}")
            script.chmod(0o755)

    def on(  # ruff: ignore[too-many-arguments] (each is an independent knob)
        self,
        name: str,
        match: str = "",
        *,
        stdout: str = "",
        code: int = 0,
        times: int = -1,
        sleep: float = 0,
    ) -> None:
        """Answer calls of name whose arguments contain match.

        Rules apply in the order added, each at most times times (or always).
        """
        self.install(name)
        self.rules.append({
            "name": name,
            "match": match,
            "stdout": stdout,
            "code": code,
            "times": times,
            "sleep": sleep,
        })
        self.save()

    def calls(self, name: str) -> list[list[str]]:
        """The arguments of each call of name, in order."""
        log = self.root / "calls.jsonl"
        if not log.exists():
            return []
        lines = log.read_text().splitlines()
        return [call[1:] for call in map(json.loads, lines) if call[0] == name]


@pytest.fixture
def commands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeCommands:
    """Fake external commands; git and Python stay real."""
    fake = FakeCommands(tmp_path / "commands")
    monkeypatch.setenv("FAKE_COMMANDS", str(fake.root))
    monkeypatch.setenv("PATH", f"{fake.bin}{os.pathsep}{os.environ['PATH']}")
    return fake
