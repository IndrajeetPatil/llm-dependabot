"""Names and locations shared across the package."""

from pathlib import Path

# The CLI runs from its checkout, which holds config.yaml, private.yaml, and
# the app's sources: src/llm_dependabot/paths.py is two levels below it.
ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILE = ROOT / "config.yaml"
PRIVATE_FILE = ROOT / "private.yaml"
APP_SOURCE = ROOT / "app"
BREWFILE = ROOT / "Brewfile"
DASHBOARD_FILE = ROOT / "dashboard.html"

NAME = "llm-dependabot"
APP_NAME = "LLM Dependabot"
BUNDLE_ID = f"com.indrajeetpatil.{NAME}"
LAUNCH_AGENTS = Path.home() / "Library/LaunchAgents"
LOG_DIR = Path.home() / "Library/Logs" / NAME
STATE_DIR = Path.home() / "Library/Application Support" / NAME
STATE_FILE = STATE_DIR / "state.json"
# Serialises runs and cleanups across processes; filelock creates STATE_DIR.
LOCK_FILE = STATE_DIR / "lock"
WORKTREE_ROOT = Path.home() / "Library/Caches" / NAME / "worktrees"
APP_BUNDLE = STATE_DIR / f"{APP_NAME}.app"
LAUNCHER = APP_BUNDLE / "Contents/MacOS" / NAME
FULL_DISK_ACCESS_PANE = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"
)
