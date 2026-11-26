"""Tests for installing the app and the launchd agents together."""

import plistlib
from typing import TYPE_CHECKING

import pytest
import typer

from llm_dependabot import install, launchd
from llm_dependabot.install import install_agents

if TYPE_CHECKING:
    from pathlib import Path

    from llm_dependabot.config import Config
    from tests.conftest import FakeCommands

PYTHON = "com.example.llm-dependabot.python"
CLEANUP = "com.example.llm-dependabot.cleanup"


@pytest.fixture
def launchctl(
    commands: FakeCommands,
    monkeypatch: pytest.MonkeyPatch,
    config: Config,
) -> FakeCommands:
    """Fake launchctl, with the app already built."""
    commands.install("launchctl")
    monkeypatch.setattr(install, "build_app", lambda built_for: built_for is not config)
    monkeypatch.setattr(launchd.os, "getuid", lambda: 501)
    return commands


def test_install_replaces_every_agent(
    launchctl: FakeCommands,
    config: Config,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Stale agents are unloaded, and every desired one is written and loaded."""
    install.LAUNCH_AGENTS.mkdir(parents=True)
    install.LOG_DIR.mkdir(parents=True)
    # One from a removed group, and one installed under an earlier prefix.
    stale = [
        install.LAUNCH_AGENTS / "com.example.llm-dependabot.old.plist",
        install.LAUNCH_AGENTS / "org.previous.llm-dependabot.python.plist",
    ]
    for path in stale:
        path.write_bytes(b"")
    install_agents(config)
    assert not any(path.exists() for path in stale)
    plist = plistlib.loads((install.LAUNCH_AGENTS / f"{PYTHON}.plist").read_bytes())
    assert plist["Label"] == PYTHON
    loaded = [call for call in launchctl.calls("launchctl") if call[0] == "bootstrap"]
    assert loaded == [
        ["bootstrap", "gui/501", str(install.LAUNCH_AGENTS / f"{label}.plist")]
        for label in (PYTHON, "com.example.llm-dependabot.rest", CLEANUP)
    ]
    out = capsys.readouterr().out
    assert f"] loaded {PYTHON}\n" in out
    assert "built" not in out


def test_install_creates_missing_directories(
    launchctl: FakeCommands,
    config: Config,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Installing creates the log and launch agent directories and their parents."""
    agents = tmp_path / "new/LaunchAgents"
    monkeypatch.setattr(install, "LAUNCH_AGENTS", agents)
    monkeypatch.setattr(launchd, "LAUNCH_AGENTS", agents)
    install_agents(config)
    assert install.LOG_DIR.is_dir()
    assert (agents / f"{PYTHON}.plist").exists()
    assert launchctl.calls("launchctl")


def test_install_reports_a_new_app_build(
    launchctl: FakeCommands,
    config: Config,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A rebuilt app is logged, since it needs Full Disk Access again."""
    monkeypatch.setattr(install, "build_app", lambda built_for: built_for is config)
    install_agents(config)
    assert f"built {install.APP_BUNDLE}" in capsys.readouterr().out
    assert launchctl.calls("launchctl")


def test_install_refuses_to_interrupt_a_run(
    launchctl: FakeCommands,
    config: Config,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Reinstalling would stop a running job, so installing waits for it."""
    install.LAUNCH_AGENTS.mkdir(parents=True)
    for label in (PYTHON, CLEANUP):
        (install.LAUNCH_AGENTS / f"{label}.plist").write_bytes(b"")
    launchctl.on("launchctl", "print", stdout="\tstate = running\n")
    with pytest.raises(typer.Exit):
        install_agents(config)
    assert f"{CLEANUP}, {PYTHON} is running;" in capsys.readouterr().err
    assert (install.LAUNCH_AGENTS / f"{PYTHON}.plist").exists()


def test_install_stops_when_an_agent_will_not_load(
    launchctl: FakeCommands,
    config: Config,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A launchctl refusal stops the install with its reason."""
    launchctl.on("launchctl", "bootstrap", code=5, times=1)
    with pytest.raises(typer.Exit):
        install_agents(config)
    assert "launchctl bootstrap" in capsys.readouterr().err
