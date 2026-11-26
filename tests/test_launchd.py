"""Tests for the launchd agents' plists."""

import shlex
from pathlib import Path
from typing import TYPE_CHECKING

from llm_dependabot import launchd
from llm_dependabot.launchd import cli_command, desired_agents

if TYPE_CHECKING:
    import pytest

    from llm_dependabot.config import Config


def test_each_group_runs_on_its_weekday_and_time(config: Config) -> None:
    """Each group's agent fires on its weekday and time."""
    agents = desired_agents(config)
    assert sorted(agents) == [
        "com.indrajeetpatil.llm-dependabot.cleanup",
        "com.indrajeetpatil.llm-dependabot.python",
        "com.indrajeetpatil.llm-dependabot.rest",
    ]
    python = agents["com.indrajeetpatil.llm-dependabot.python"]
    # launchd counts weekdays from Sunday as 0.
    assert python["StartCalendarInterval"] == {"Weekday": 2, "Hour": 11, "Minute": 0}
    rest = agents["com.indrajeetpatil.llm-dependabot.rest"]
    assert rest["StartCalendarInterval"] == {"Weekday": 3, "Hour": 9, "Minute": 30}
    assert rest["StandardOutPath"] == str(launchd.LOG_DIR / "rest.log")


def test_jobs_start_through_the_app_in_a_login_shell(config: Config) -> None:
    """Every job starts through the app's launcher in a login shell."""
    for plist in desired_agents(config).values():
        program = plist["ProgramArguments"]
        assert program[:5] == [str(launchd.LAUNCHER), "/bin/zsh", "-l", "-i", "-c"]
        assert plist["AssociatedBundleIdentifiers"] == [
            "com.indrajeetpatil.llm-dependabot"
        ]


def test_the_cleanup_runs_at_load_and_on_an_interval(config: Config) -> None:
    """The cleanup agent runs at load and every interval."""
    cleanup = desired_agents(config)["com.indrajeetpatil.llm-dependabot.cleanup"]
    assert cleanup["StartInterval"] == 3 * 3600
    assert cleanup["RunAtLoad"] is True
    assert shlex.split(cleanup["ProgramArguments"][-1])[-2:] == [
        "cleanup",
        "--scheduled",
    ]


def test_the_cli_command_quotes_the_checkout(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI command survives spaces in paths and names."""
    monkeypatch.setattr(launchd, "ROOT", Path("/Users/me/My Projects/bot"))
    command = cli_command("run", "web apps", "--scheduled")
    assert command.startswith("exec ")
    assert shlex.split(command.removeprefix("exec ")) == [
        "uv",
        "run",
        "--project",
        "/Users/me/My Projects/bot",
        "--locked",
        "--no-dev",
        "llm-dependabot",
        "run",
        "web apps",
        "--scheduled",
    ]
