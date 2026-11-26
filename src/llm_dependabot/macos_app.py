"""The LLM Dependabot app, which holds the Full Disk Access grant."""

import json
import re
import shutil
import time
from pathlib import Path
from typing import Any
lazy import hashlib
lazy import plistlib
lazy import tempfile

import typer

from llm_dependabot.launchd import gui_domain, launchctl
from llm_dependabot.paths import (
    APP_BUNDLE,
    APP_NAME,
    APP_SOURCE,
    BUNDLE_ID,
    FULL_DISK_ACCESS_PANE,
    LAUNCHER,
    NAME,
    STATE_DIR,
)
from llm_dependabot.shell import sh


def app_info() -> dict[str, Any]:
    """The app's Info.plist."""
    return {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleExecutable": NAME,
        "CFBundleIconFile": "AppIcon",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "1.0",
        "LSUIElement": True,  # no Dock icon
    }


def build_icon(source: Path, icns: Path) -> None:
    """Convert a PNG into the app's icns icon."""
    with tempfile.TemporaryDirectory(suffix=".iconset") as iconset:
        for size in (16, 32, 128, 256, 512):
            for scale, suffix in ((1, ""), (2, "@2x")):
                out = Path(iconset) / f"icon_{size}x{size}{suffix}.png"
                pixels = str(size * scale)
                sh("sips", "-z", pixels, pixels, source, "--out", out)
        sh("iconutil", "-c", "icns", iconset, "-o", icns)


def build_app() -> bool:
    """Build the LLM Dependabot app; return True if it changed.

    macOS ties the Full Disk Access grant to the app's code signature, so the
    app is rebuilt, and needs granting again, only when its sources change.
    """
    sources = [APP_SOURCE / "launcher.c", APP_SOURCE / "icon.png"]
    digest = hashlib.sha256()
    for path in sources:
        digest.update(path.read_bytes())
    digest.update(json.dumps(app_info(), sort_keys=True).encode())
    stamp = STATE_DIR / "app.sha256"
    if LAUNCHER.exists() and stamp.exists() and stamp.read_text() == digest.hexdigest():
        return False

    shutil.rmtree(APP_BUNDLE, ignore_errors=True)
    contents = APP_BUNDLE / "Contents"
    (contents / "Resources").mkdir(parents=True)
    LAUNCHER.parent.mkdir()
    (contents / "Info.plist").write_bytes(plistlib.dumps(app_info()))
    sh("clang", "-O2", "-Wall", "-Werror", "-o", LAUNCHER, sources[0])
    build_icon(sources[1], contents / "Resources/AppIcon.icns")
    sh("codesign", "--force", "--sign", "-", "--identifier", BUNDLE_ID, APP_BUNDLE)
    stamp.write_text(digest.hexdigest())
    return True


def full_disk_access_granted(path: Path) -> bool:
    """Check that a launchd job started through the app can read path.

    This runs a throwaway agent, so it exercises the same privacy checks as
    the scheduled jobs rather than those of the current terminal. A job
    without access may instead hang on a privacy prompt; it is stopped after
    ten seconds and counts as not granted.
    """
    label = f"{BUNDLE_ID}.access-check"
    plist_path = STATE_DIR / f"{label}.plist"
    plist_path.write_bytes(
        plistlib.dumps({
            "Label": label,
            "ProgramArguments": [str(LAUNCHER), "/bin/ls", str(path)],
            "RunAtLoad": True,
            "StandardOutPath": "/dev/null",
            "StandardErrorPath": "/dev/null",
        })
    )
    target = f"{gui_domain()}/{label}"
    launchctl("bootout", target)
    launchctl("bootstrap", gui_domain(), plist_path)
    code = None
    for _ in range(100):
        if match := re.search(
            r"last exit code = (\d+)", launchctl("print", target).stdout
        ):
            code = int(match[1])
            break
        time.sleep(0.1)
    launchctl("bootout", target)
    plist_path.unlink(missing_ok=True)
    return code == 0


def show_full_disk_access_steps() -> None:
    """Explain how to grant Full Disk Access, and open the settings."""
    typer.echo(
        "\nmacOS blocks launchd jobs from ~/Documents and similar folders unless"
        f" their program has Full Disk Access. Drag {APP_NAME} from the Finder"
        " window into System Settings > Privacy & Security > Full Disk Access"
        " (or click + and choose it), then switch it on:\n"
        f"  {APP_BUNDLE}\n"
        f"If macOS instead asks whether {APP_NAME} may access a folder, the"
        " check timed out waiting for it; dismiss the prompt and use the"
        " setting above.\n"
    )
    typer.launch(FULL_DISK_ACCESS_PANE)
    typer.launch(str(APP_BUNDLE), locate=True)
