"""The steps of the interactive first-time setup."""

import re
import shutil
from typing import TYPE_CHECKING

import typer
lazy import yaml

from llm_dependabot.discovery import prompts_in
from llm_dependabot.github import owned_repos
from llm_dependabot.install import install_agents
from llm_dependabot.macos_app import (
    full_disk_access_granted,
    show_full_disk_access_steps,
)
from llm_dependabot.paths import APP_NAME, BREWFILE, CONFIG_FILE, PRIVATE_FILE
from llm_dependabot.shell import fail, interactive, sh, succeeds

if TYPE_CHECKING:
    from llm_dependabot.config import Config


def step(title: str) -> None:
    """Print a setup step's heading."""
    typer.secho(f"\n==> {title}", bold=True)


def pause(message: str) -> None:
    """Wait for the user to press Enter."""
    typer.prompt(f"{message} Press Enter to continue", default="", show_default=False)


def ensure_brew_bundle() -> None:
    """Check that every Brewfile package is installed."""
    step("Homebrew packages (Brewfile)")
    if not succeeds("brew", "bundle", "check", "--no-upgrade", "--file", BREWFILE):
        fail(
            "some Brewfile packages are missing; run `make setup`, which installs them"
        )
    typer.echo("installed")


def ensure_signed_in(config: Config) -> None:
    """Wait until gh and the agent are both signed in."""
    step("GitHub CLI sign-in")
    while not succeeds("gh", "auth", "status"):
        if not typer.confirm(
            "gh is not signed in. Run `gh auth login` now?", default=True
        ):
            fail("gh must be signed in")
        interactive("gh", "auth", "login")
    typer.echo("signed in")

    agent = config.agent
    step(f"{agent.name} sign-in")
    if shutil.which(agent.command[0]) is None:
        fail(
            f"{agent.command[0]} is not installed; add its package to the Brewfile"
            " and rerun `make setup`"
        )
    if agent.check is None:
        typer.echo(f"no sign-in check configured; make sure {agent.name} is signed in")
        return
    while not succeeds(*agent.check):
        typer.echo(
            f"`{' '.join(agent.check)}` failed. Run `{agent.command[0]}` in another"
            " terminal and sign in."
        )
        pause("Once signed in, come back here.")
    typer.echo("signed in")


def check_owner(config: Config) -> None:
    """Offer to set owner in config.yaml to the signed-in GitHub account."""
    step("Repository owner")
    login = sh("gh", "api", "user", "--jq", ".login")
    if login.lower() == config.owner.lower():
        typer.echo(f"{CONFIG_FILE.name} owner {config.owner!r} matches your account")
        return
    typer.echo(
        f"{CONFIG_FILE.name} names {config.owner!r}, but gh is signed in as {login!r}."
    )
    if typer.confirm(f"Set owner to {login!r} in {CONFIG_FILE.name}?", default=True):
        text = CONFIG_FILE.read_text()
        CONFIG_FILE.write_text(
            re.sub(r"^owner: .*$", f"owner: {login}", text, count=1, flags=re.MULTILINE)
        )
        config.owner = login


def ensure_clone_root(config: Config) -> None:
    """Offer to create clone_root if it does not exist."""
    step("Clone directory")
    root = config.clone_root
    if not root.is_dir():
        if not typer.confirm(f"{root} does not exist. Create it?", default=True):
            fail(f"set clone_root in {CONFIG_FILE.name} to an existing directory")
        root.mkdir(parents=True)
    typer.echo(str(root))


def choose_private_repos(config: Config) -> None:
    """Ask which private repositories with prompts to include."""
    step("Private repositories")
    if PRIVATE_FILE.exists():
        typer.echo(
            f"{PRIVATE_FILE.name} already lists"
            f" {len(config.private_repos)} repositories"
        )
        if not typer.confirm(f"Choose them again (rewrites {PRIVATE_FILE.name})?"):
            return
    candidates = [
        item.name
        for item in owned_repos(config, "private")
        if prompts_in(item.repo(config.owner), config)
    ]
    if not candidates:
        typer.echo("no private repositories contain any of the configured prompts")
    chosen = [
        name
        for name in candidates
        if typer.confirm(f"Include private repository {name}?", default=True)
    ]
    data = {"repos": chosen}
    PRIVATE_FILE.write_text(
        "# Private repositories to include; git-ignored, never commit it.\n\n"
        + yaml.safe_dump(data, sort_keys=False)
    )
    config.private_repos = frozenset(chosen)
    typer.echo(f"wrote {PRIVATE_FILE.name} with {len(chosen)} repositories")


def install_git_hooks() -> None:
    """Install the prek git hooks."""
    step("Git hooks")
    if interactive("prek", "install") != 0:
        fail("prek install failed")


def ensure_full_disk_access(config: Config) -> None:
    """Install the app and agents, then wait for Full Disk Access."""
    step(f"{APP_NAME} app, launchd agents, and Full Disk Access")
    install_agents(config)
    while not full_disk_access_granted(config):
        show_full_disk_access_steps()
        pause(f"Once {APP_NAME} is switched on,")
    typer.echo(f"scheduled jobs can read {config.clone_root}")


def run_setup(config: Config) -> None:
    """Check prerequisites and sign-ins, then install everything in turn."""
    ensure_brew_bundle()
    ensure_signed_in(config)
    check_owner(config)
    ensure_clone_root(config)
    choose_private_repos(config)
    install_git_hooks()
    ensure_full_disk_access(config)
