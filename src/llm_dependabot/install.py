"""Install the app and the launchd agents together."""

import plistlib
from typing import TYPE_CHECKING

from llm_dependabot.launchd import (
    desired_agents,
    gui_domain,
    installed_labels,
    launchctl,
    running_jobs,
    unload,
)
from llm_dependabot.macos_app import build_app
from llm_dependabot.paths import APP_BUNDLE, LAUNCH_AGENTS, LOG_DIR
from llm_dependabot.shell import fail, log

if TYPE_CHECKING:
    from llm_dependabot.config import Config


def install_agents(config: Config) -> None:
    """Build the app, then write and load the launchd agents."""
    if busy := running_jobs():
        fail(
            f"{', '.join(busy)} is running; reinstalling would stop it."
            " Try again once it finishes (see `status`).",
        )
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if build_app(config):
        log(f"built {APP_BUNDLE}")
    for label in installed_labels():
        unload(label)
    LAUNCH_AGENTS.mkdir(parents=True, exist_ok=True)
    for label, plist in desired_agents(config).items():
        path = LAUNCH_AGENTS / f"{label}.plist"
        path.write_bytes(plistlib.dumps(plist))
        result = launchctl("bootstrap", gui_domain(), path)
        if result.returncode != 0:
            fail(f"launchctl bootstrap {label} failed: {result.stderr.strip()}")
        log(f"loaded {label}")
