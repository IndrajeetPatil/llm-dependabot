"""Tests for building the app and checking its Full Disk Access grant."""

import hashlib
import json
import plistlib
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from llm_dependabot import macos_app
from llm_dependabot.macos_app import (
    build_app,
    full_disk_access_granted,
    show_full_disk_access_steps,
)

if TYPE_CHECKING:
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


INFO: dict[str, Any] = {
    "CFBundleName": "LLM Dependabot",
    "CFBundleDisplayName": "LLM Dependabot",
    "CFBundleIdentifier": "com.example.llm-dependabot",
    "CFBundleExecutable": "llm-dependabot",
    "CFBundleIconFile": "AppIcon",
    "CFBundlePackageType": "APPL",
    "CFBundleShortVersionString": "1.0",
    "LSUIElement": True,
}


def test_build_app_commands(toolchain: FakeCommands, config: Config) -> None:
    """The bundle's layout, and the exact compile, icon, and signing commands."""
    build_app(config)
    bundle = macos_app.APP_BUNDLE
    assert sorted(str(p.relative_to(bundle)) for p in bundle.rglob("*")) == [
        "Contents",
        "Contents/Info.plist",
        "Contents/MacOS",
        "Contents/Resources",
    ]
    info_plist = (bundle / "Contents/Info.plist").read_bytes()
    assert plistlib.loads(info_plist) == INFO
    source = macos_app.APP_SOURCE
    assert toolchain.calls("clang") == [
        [
            "-O2",
            "-Wall",
            "-Werror",
            "-o",
            str(macos_app.LAUNCHER),
            str(source / "launcher.c"),
        ],
    ]
    sips = toolchain.calls("sips")
    iconset = Path(sips[0][-1]).parent
    assert iconset.name.endswith(".iconset")
    assert sips == [
        ["-z", pixels, pixels, str(source / "icon.png"), "--out", str(iconset / name)]
        for size in (16, 32, 128, 256, 512)
        for pixels, name in (
            (str(size), f"icon_{size}x{size}.png"),
            (str(size * 2), f"icon_{size}x{size}@2x.png"),
        )
    ]
    icns = bundle / "Contents/Resources/AppIcon.icns"
    assert toolchain.calls("iconutil") == [
        ["-c", "icns", str(iconset), "-o", str(icns)],
    ]
    assert toolchain.calls("codesign") == [
        [
            "--force",
            "--sign",
            "-",
            "--identifier",
            "com.example.llm-dependabot",
            str(bundle),
        ],
    ]
    digest = hashlib.sha256()
    for name in ("launcher.c", "icon.png"):
        digest.update((source / name).read_bytes())
    digest.update(json.dumps(INFO, sort_keys=True).encode())
    assert [p.name for p in macos_app.STATE_DIR.iterdir() if p.is_file()] == [
        "app.sha256",
    ]
    stamp = macos_app.STATE_DIR / "app.sha256"
    assert stamp.read_text() == digest.hexdigest()


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
    calls: list[tuple[str | Path, ...]] = []
    loaded: list[dict[str, Any]] = []
    label = "com.example.llm-dependabot.access-check"
    plist = macos_app.STATE_DIR / f"{label}.plist"

    def launchctl(*args: str | Path) -> subprocess.CompletedProcess[str]:
        """Record the call, and report the job's state when printed."""
        calls.append(args)
        if args[0] == "bootstrap":
            loaded.append(plistlib.loads(plist.read_bytes()))
        stdout = printed if args[0] == "print" else ""
        return subprocess.CompletedProcess(list(map(str, args)), 0, stdout, "")

    sleeps: list[float] = []
    monkeypatch.setattr(macos_app, "launchctl", launchctl)
    monkeypatch.setattr(macos_app, "gui_domain", lambda: "gui/501")
    # Skip the waits between polls without touching the shared time module.
    monkeypatch.setattr(macos_app, "time", SimpleNamespace(sleep=sleeps.append))
    macos_app.STATE_DIR.mkdir(parents=True)
    assert full_disk_access_granted(config) is granted
    target = f"gui/501/{label}"
    assert calls == [
        ("bootout", target),
        ("bootstrap", "gui/501", plist),
        *[("print", target)] * polls,
        ("bootout", target),
    ]
    assert sleeps == [0.1] * (polls if polls > 1 else 0)
    assert loaded == [
        {
            "Label": label,
            "ProgramArguments": [
                str(macos_app.LAUNCHER),
                "/bin/ls",
                str(config.clone_root),
            ],
            "RunAtLoad": True,
            "StandardOutPath": "/dev/null",
            "StandardErrorPath": "/dev/null",
        },
    ]
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
    assert capsys.readouterr().out == (
        "\nmacOS blocks launchd jobs from ~/Documents and similar folders unless"
        " their program has Full Disk Access. Drag LLM Dependabot from the Finder"
        " window into System Settings > Privacy & Security > Full Disk Access"
        " (or click + and choose it), then switch it on:\n"
        f"  {macos_app.APP_BUNDLE}\n"
        "If macOS instead asks whether LLM Dependabot may access a folder, the"
        " check timed out waiting for it; dismiss the prompt and use the"
        " setting above.\n\n"
    )
