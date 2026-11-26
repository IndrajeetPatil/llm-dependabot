"""The launchd agents that start each group's run and the cleanup."""

import os
import re
import shlex
import subprocess
from typing import TYPE_CHECKING, Any

from llm_dependabot.config import WEEKDAYS
from llm_dependabot.paths import LAUNCH_AGENTS, LAUNCHER, LOG_DIR, NAME, ROOT

if TYPE_CHECKING:
    from pathlib import Path

    from llm_dependabot.config import Config


def launchctl(*args: str | Path) -> subprocess.CompletedProcess[str]:
    """Run launchctl, capturing its output without checking its exit code."""
    return subprocess.run(
        ["launchctl", *args],
        capture_output=True,
        encoding="utf-8",
        check=False,
    )


def gui_domain() -> str:
    """The launchd domain of the logged-in user's agents."""
    return f"gui/{os.getuid()}"


def cli_command(*args: str) -> str:
    """A shell command that runs the CLI from this checkout's locked environment."""
    argv = ["uv", "run", "--project", str(ROOT), "--locked", "--no-dev"]
    return "exec " + shlex.join([*argv, "llm-dependabot", *args])


def plist_for(
    config: Config,
    job: str,
    shell_command: str,
    schedule: dict[str, Any],
) -> dict[str, Any]:
    """A launchd agent that runs the shell command through the app."""
    return {
        "Label": config.launchd_label(job),
        # Shows the jobs as "LLM Dependabot" in System Settings > General >
        # Login Items rather than as a bare shell.
        "AssociatedBundleIdentifiers": [config.bundle_id],
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
        "StandardOutPath": str(LOG_DIR / f"{job}.log"),
        "StandardErrorPath": str(LOG_DIR / f"{job}.log"),
        **schedule,
    }


def desired_agents(config: Config) -> dict[str, dict[str, Any]]:
    """Every launchd agent the configuration calls for, by label."""
    agents = {}
    for group in config.groups:
        when = {
            "Weekday": WEEKDAYS.index(group.weekday),
            "Hour": group.time.hour,
            "Minute": group.time.minute,
        }
        agents[config.launchd_label(group.name)] = plist_for(
            config,
            group.name,
            cli_command("run", group.name, "--scheduled"),
            {"StartCalendarInterval": when},
        )
    agents[config.launchd_label("cleanup")] = plist_for(
        config,
        "cleanup",
        cli_command("cleanup", "--scheduled"),
        {"StartInterval": int(config.cleanup_interval_hours * 3600), "RunAtLoad": True},
    )
    return agents


def unload(label: str) -> None:
    """Stop and remove a launchd agent."""
    launchctl("bootout", f"{gui_domain()}/{label}")
    (LAUNCH_AGENTS / f"{label}.plist").unlink(missing_ok=True)


def installed_labels() -> list[str]:
    """Labels of the installed launchd agents.

    Agents are matched by the tool's name rather than the configured prefix,
    so those installed under an earlier `bundle_id_prefix` are still found,
    and replaced or removed.
    """
    return sorted(p.stem for p in LAUNCH_AGENTS.glob(f"*.{NAME}.*.plist"))


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
