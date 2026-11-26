"""Tests for building the app and checking its Full Disk Access grant."""

import plistlib
import subprocess
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from llm_dependabot import macos_app
from llm_dependabot.macos_app import (
    build_app,
    full_disk_access_granted,
    show_full_disk_access_steps,
)

if TYPE_CHECKING:
    from pathlib import Path

    from llm_dependabot.config import Config
    from tests.conftest import FakeCommands


@pytest.fixture
def toolchain(commands: FakeCommands) -> FakeCommands:
    """Fake the compiler, image tools, and code signing the build calls."""
    commands.install("clang", "sips", "iconutil", "codesign")
    return commands


def test_build_app_builds_once_until_its_sources_change(
    toolchain: FakeCommands,
    config: Config,
) -> None:
    """The app is compiled, iconified, and signed, then left alone while unchanged."""
    assert build_app(config) is True
    info = plistlib.loads((macos_app.APP_BUNDLE / "Contents/Info.plist").read_bytes())
    assert info["CFBundleIdentifier"] == "com.example.llm-dependabot"
    assert info["LSUIElement"] is True
    [clang] = toolchain.calls("clang")
    assert clang[-3:] == [
        "-o",
        str(macos_app.LAUNCHER),
        str(macos_app.APP_SOURCE / "launcher.c"),
    ]
    assert len(toolchain.calls("sips")) == 10  # five sizes, each at 1x and 2x
    assert len(toolchain.calls("iconutil")) == 1
    assert toolchain.calls("codesign")[0][-1] == str(macos_app.APP_BUNDLE)

    # Fake clang writes nothing, so stand in for the launcher it would build.
    macos_app.LAUNCHER.write_bytes(b"")
    assert build_app(config) is False
    assert len(toolchain.calls("clang")) == 1

    (macos_app.STATE_DIR / "app.sha256").write_text("stale")
    assert build_app(config) is True

    macos_app.LAUNCHER.write_bytes(b"")
    renamed = config.model_copy(update={"bundle_id_prefix": "org.example"})
    assert build_app(renamed) is True
    info = plistlib.loads((macos_app.APP_BUNDLE / "Contents/Info.plist").read_bytes())
    assert info["CFBundleIdentifier"] == "org.example.llm-dependabot"


@pytest.mark.parametrize(
    ("printed", "granted", "polls"),
    [
        pytest.param("last exit code = 0\n", True, 1, id="listed the folder"),
        pytest.param("last exit code = 1\n", False, 1, id="was refused"),
        pytest.param("state = running\n", False, 100, id="never finished"),
    ],
)
def test_full_disk_access_granted(
    monkeypatch: pytest.MonkeyPatch,
    config: Config,
    printed: str,
    polls: int,
    *,
    granted: bool,
) -> None:
    """A throwaway agent that lists the folder through the app tells.

    launchctl is faked in-process here: the check polls it up to a hundred
    times, and test_launchd already runs the real subprocess path.
    """
    verbs: list[str] = []

    def launchctl(*args: str | Path) -> subprocess.CompletedProcess[str]:
        """Record the verb, and report the job's state when printed."""
        verbs.append(str(args[0]))
        stdout = printed if args[0] == "print" else ""
        return subprocess.CompletedProcess(list(map(str, args)), 0, stdout, "")

    monkeypatch.setattr(macos_app, "launchctl", launchctl)
    # Skip the waits between polls without touching the shared time module.
    monkeypatch.setattr(macos_app, "time", SimpleNamespace(sleep=lambda _s: None))
    macos_app.STATE_DIR.mkdir(parents=True)
    assert full_disk_access_granted(config) is granted
    assert verbs == ["bootout", "bootstrap", *["print"] * polls, "bootout"]
    assert list(macos_app.STATE_DIR.iterdir()) == []


def test_show_full_disk_access_steps_opens_settings_and_the_app(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The steps open the privacy pane and reveal the app in the Finder."""
    launched: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        macos_app.typer,
        "launch",
        lambda url, *, locate=False: launched.append((url, locate)),
    )
    show_full_disk_access_steps()
    assert launched == [
        (macos_app.FULL_DISK_ACCESS_PANE, False),
        (str(macos_app.APP_BUNDLE), True),
    ]
    assert str(macos_app.APP_BUNDLE) in capsys.readouterr().out
