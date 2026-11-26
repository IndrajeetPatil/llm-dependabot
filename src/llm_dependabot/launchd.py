"""The launchd agents that start each group's run and the cleanup."""

import os
import re
import subprocess
from typing import TYPE_CHECKING, Any
lazy import shlex

from llm_dependabot.config import WEEKDAYS
from llm_dependabot.paths import BUNDLE_ID, LAUNCH_AGENTS, LAUNCHER, LOG_DIR, ROOT

if TYPE_CHECKING:
    from pathlib import Path

    from llm_dependabot.config import Config


def launchctl(*args: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["launchctl", *args], capture_output=True, text=True, check=False
    )


def gui_domain() -> str:
    return f"gui/{os.getuid()}"


def cli_command(*args: str) -> str:
    """A shell command that runs the CLI from this checkout's locked environment."""
    argv = ["uv", "run", "--project", str(ROOT), "--locked", "--no-dev"]
    return "exec " + shlex.join([*argv, "llm-dependabot", *args])


def plist_for(
    label: str, shell_command: str, schedule: dict[str, Any], log_name: str
) -> dict[str, Any]:
    return {
        "Label": label,
        # Shows the jobs as "LLM Dependabot" in System Settings > General >
        # Login Items rather than as a bare shell.
        "AssociatedBundleIdentifiers": [BUNDLE_ID],
        # The app's launcher holds the Full Disk Access grant (see
        # app/launcher.c). A login, interactive zsh picks up the same PATH
        # (Homebrew, uv, pnpm, the agent, gh) and keychain-backed credentials as a
        # terminal session.
        "ProgramArguments": [
            str(LAUNCHER),
            "/bin/zsh",
            "-l",
            "-i",
            "-c",
            shell_command,
        ],
        "StandardOutPath": str(LOG_DIR / log_name),
        "StandardErrorPath": str(LOG_DIR / log_name),
        **schedule,
    }


def desired_agents(config: Config) -> dict[str, dict[str, Any]]:
    agents = {}
    for group in config.groups:
        when = {
            "Weekday": WEEKDAYS.index(group.weekday),
            "Hour": group.time.hour,
            "Minute": group.time.minute,
        }
        agents[group.label] = plist_for(
            group.label,
            cli_command("run", group.name, "--scheduled"),
            {"StartCalendarInterval": when},
            f"{group.name}.log",
        )
    label = f"{BUNDLE_ID}.cleanup"
    agents[label] = plist_for(
        label,
        cli_command("cleanup", "--scheduled"),
        {"StartInterval": int(config.cleanup_interval_hours * 3600), "RunAtLoad": True},
        "cleanup.log",
    )
    return agents


def unload(label: str) -> None:
    launchctl("bootout", f"{gui_domain()}/{label}")
    (LAUNCH_AGENTS / f"{label}.plist").unlink(missing_ok=True)


def installed_labels() -> list[str]:
    return sorted(p.stem for p in LAUNCH_AGENTS.glob(f"{BUNDLE_ID}.*.plist"))


def running_jobs() -> list[str]:
    """Labels of installed agents whose job is running right now."""
    return [
        label
        for label in installed_labels()
        if re.search(
            r"^\tstate = running$",
            launchctl("print", f"{gui_domain()}/{label}").stdout,
            re.MULTILINE,
        )
    ]
