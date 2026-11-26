"""Tests for installing the app and the launchd agents together."""

import plistlib
from typing import TYPE_CHECKING

import pytest
import typer

from llm_dependabot import install
from llm_dependabot.install import install_agents

if TYPE_CHECKING:
    from llm_dependabot.config import Config
    from tests.conftest import FakeCommands

PYTHON = "com.indrajeetpatil.llm-dependabot.python"


@pytest.fixture
def launchctl(commands: FakeCommands, monkeypatch: pytest.MonkeyPatch) -> FakeCommands:
    """Fake launchctl, with the app already built."""
    commands.install("launchctl")
    monkeypatch.setattr(install, "build_app", lambda: False)
    return commands


def test_install_replaces_every_agent(launchctl: FakeCommands, config: Config) -> None:
    """Stale agents are unloaded, and every desired one is written and loaded."""
    install.LAUNCH_AGENTS.mkdir(parents=True)
    stale = install.LAUNCH_AGENTS / "com.indrajeetpatil.llm-dependabot.old.plist"
    stale.write_bytes(b"")
    install_agents(config)
    assert not stale.exists()
    plist = plistlib.loads((install.LAUNCH_AGENTS / f"{PYTHON}.plist").read_bytes())
    assert plist["Label"] == PYTHON
    loaded = [call for call in launchctl.calls("launchctl") if call[0] == "bootstrap"]
    assert len(loaded) == 3  # two groups and the cleanup
    assert install.LOG_DIR.is_dir()


def test_install_reports_a_new_app_build(
    launchctl: FakeCommands,
    config: Config,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A rebuilt app is logged, since it needs Full Disk Access again."""
    monkeypatch.setattr(install, "build_app", lambda: True)
    install_agents(config)
    assert f"built {install.APP_BUNDLE}" in capsys.readouterr().out
    assert launchctl.calls("launchctl")


def test_install_refuses_to_interrupt_a_run(
    launchctl: FakeCommands, config: Config, capsys: pytest.CaptureFixture[str]
) -> None:
    """Reinstalling would stop a running job, so installing waits for it."""
    install.LAUNCH_AGENTS.mkdir(parents=True)
    (install.LAUNCH_AGENTS / f"{PYTHON}.plist").write_bytes(b"")
    launchctl.on("launchctl", "print", stdout="\tstate = running\n")
    with pytest.raises(typer.Exit):
        install_agents(config)
    assert f"{PYTHON} is running" in capsys.readouterr().err
    assert (install.LAUNCH_AGENTS / f"{PYTHON}.plist").exists()


def test_install_stops_when_an_agent_will_not_load(
    launchctl: FakeCommands, config: Config, capsys: pytest.CaptureFixture[str]
) -> None:
    """A launchctl refusal stops the install with its reason."""
    launchctl.on("launchctl", "bootstrap", code=5, times=1)
    with pytest.raises(typer.Exit):
        install_agents(config)
    assert "launchctl bootstrap" in capsys.readouterr().err
