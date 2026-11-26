"""Fixtures shared by every test: an isolated home and a valid config."""

import json
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
