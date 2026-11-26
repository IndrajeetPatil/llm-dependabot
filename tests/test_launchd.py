"""Tests for the launchd agents' plists."""

import shlex
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from llm_dependabot import launchd
from llm_dependabot.launchd import cli_command, desired_agents

if TYPE_CHECKING:
    from collections.abc import Callable

    from llm_dependabot.config import Config
    from tests.conftest import FakeCommands, Spy


def test_there_is_one_agent_per_group_plus_the_cleanup(config: Config) -> None:
    """Each group gets an agent, and so does the cleanup."""
    assert sorted(desired_agents(config)) == [
        "com.example.llm-dependabot.cleanup",
        "com.example.llm-dependabot.python",
        "com.example.llm-dependabot.rest",
    ]


@pytest.mark.parametrize(
    ("group", "when"),
    [
        # launchd counts weekdays from Sunday as 0.
        pytest.param("python", {"Weekday": 2, "Hour": 11, "Minute": 0}, id="python"),
        pytest.param("rest", {"Weekday": 3, "Hour": 9, "Minute": 30}, id="rest"),
    ],
)
def test_each_group_runs_on_its_weekday_and_time(
    config: Config,
    group: str,
    when: dict[str, int],
) -> None:
    """Each group's agent fires on its weekday and time, and logs to its own file."""
    plist = desired_agents(config)[f"com.example.llm-dependabot.{group}"]
    assert plist["StartCalendarInterval"] == when
    assert plist["StandardOutPath"] == str(launchd.LOG_DIR / f"{group}.log")
    assert plist["StandardErrorPath"] == plist["StandardOutPath"]
    assert shlex.split(plist["ProgramArguments"][-1])[-3:] == [
        "run",
        group,
        "--scheduled",
    ]


def test_jobs_start_through_the_app_in_a_login_shell(config: Config) -> None:
    """Every job starts through the app's launcher in a login shell."""
    for plist in desired_agents(config).values():
        program = plist["ProgramArguments"]
        assert program[:5] == [str(launchd.LAUNCHER), "/bin/zsh", "-l", "-i", "-c"]
        assert plist["AssociatedBundleIdentifiers"] == ["com.example.llm-dependabot"]


def test_the_cleanup_runs_at_load_and_on_an_interval(config: Config) -> None:
    """The cleanup agent runs at load and every interval."""
    cleanup = desired_agents(config)["com.example.llm-dependabot.cleanup"]
    assert cleanup["Label"] == "com.example.llm-dependabot.cleanup"
    assert cleanup["StandardOutPath"] == str(launchd.LOG_DIR / "cleanup.log")
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


def install_plists(*labels: str) -> None:
    """Write empty plists for these launchd labels, as install does."""
    launchd.LAUNCH_AGENTS.mkdir(parents=True, exist_ok=True)
    for label in labels:
        (launchd.LAUNCH_AGENTS / f"{label}.plist").write_bytes(b"")


def test_installed_labels_lists_only_this_tools_agents() -> None:
    """Only plists named after the tool count, under any prefix, sorted."""
    install_plists(
        "com.example.llm-dependabot.rest",
        "com.example.llm-dependabot.cleanup",
        "org.previous.llm-dependabot.python",
        "com.example.other",
    )
    assert launchd.installed_labels() == [
        "com.example.llm-dependabot.cleanup",
        "com.example.llm-dependabot.rest",
        "org.previous.llm-dependabot.python",
    ]


def test_unload_boots_the_agent_out_and_deletes_its_plist(
    commands: FakeCommands,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unloading stops the job in the user's GUI domain and removes the plist."""
    monkeypatch.setattr(launchd.os, "getuid", lambda: 501)
    commands.install("launchctl")
    install_plists("com.example.llm-dependabot.rest")
    launchd.unload("com.example.llm-dependabot.rest")
    assert commands.calls("launchctl") == [
        ["bootout", "gui/501/com.example.llm-dependabot.rest"],
    ]
    assert launchd.installed_labels() == []


def test_unload_tolerates_a_missing_plist(commands: FakeCommands) -> None:
    """Unloading an agent whose plist is already gone still succeeds."""
    commands.install("launchctl")
    launchd.unload("com.example.llm-dependabot.rest")
    assert commands.calls("launchctl")


def test_launchctl_options(
    commands: FakeCommands,
    spy: Callable[[Any, str], Spy],
) -> None:
    """Launchctl's output is decoded as UTF-8, and a failure is returned."""
    commands.on("launchctl", stdout="out", code=3)
    run = spy(subprocess, "run")
    result = launchd.launchctl("print", Path("x"))
    assert (result.returncode, result.stdout) == (3, "out")
    assert run.calls == [
        (
            (["launchctl", "print", Path("x")],),
            {"capture_output": True, "encoding": "utf-8", "check": False},
        ),
    ]


def test_running_jobs_reads_each_agents_state(
    commands: FakeCommands,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A job counts as running only when launchctl says its state is running."""
    monkeypatch.setattr(launchd.os, "getuid", lambda: 501)
    install_plists(
        "com.example.llm-dependabot.python",
        "com.example.llm-dependabot.rest",
    )
    commands.on("launchctl", ".python", stdout="{\n\tstate = running\n}\n")
    commands.on("launchctl", ".rest", stdout="{\n\tstate = waiting\n}\n")
    assert launchd.running_jobs() == ["com.example.llm-dependabot.python"]
    assert commands.calls("launchctl") == [
        ["print", "gui/501/com.example.llm-dependabot.python"],
        ["print", "gui/501/com.example.llm-dependabot.rest"],
    ]
