"""Run each repository's prompts with a coding agent on a weekly or monthly cadence."""

import os
from typing import Annotated

import typer

from llm_dependabot import __version__
from llm_dependabot.checkouts import stale_checkout
from llm_dependabot.config import is_weekend, load_config
from llm_dependabot.dashboard.render import render_dashboard
from llm_dependabot.discovery import discover
from llm_dependabot.install import install_agents
from llm_dependabot.launchd import installed_labels, unload
from llm_dependabot.macos_app import (
    full_disk_access_granted,
    show_full_disk_access_steps,
)
from llm_dependabot.paths import APP_NAME, DASHBOARD_FILE, ROOT
from llm_dependabot.runner import cleanup as cleanup_pending, planned_runs, run_plan
from llm_dependabot.setup_wizard import run_setup, step
from llm_dependabot.shell import fail, log, notify
from llm_dependabot.state import load_state

app = typer.Typer(
    help=__doc__,
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)


def show_version(value: bool) -> None:  # ruff: ignore[boolean-type-hint-positional-argument] (a Typer callback)
    """Print the version and exit, for --version."""
    if value:
        typer.echo(f"llm-dependabot {__version__}")
        raise typer.Exit


@app.callback()
def main(
    *,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            callback=show_version,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ] = False,
) -> None:
    """Handle the options shared by every command."""


@app.command()
def run(
    group: str,
    repo: Annotated[
        list[str] | None,
        typer.Option(help="Limit to this repository."),
    ] = None,
    prompt: Annotated[
        list[str] | None,
        typer.Option(help="Run this prompt whatever its cadence."),
    ] = None,
    *,
    dry_run: Annotated[bool, typer.Option(help="Only list what would run.")] = False,
    scheduled: Annotated[
        bool,
        typer.Option(hidden=True, help="Started by launchd."),
    ] = False,
) -> None:
    """Run the prompts that are due in every repository in GROUP."""
    config = load_config()
    if scheduled and is_weekend(config):
        log(f"group {group}: skipped, since it is the weekend")
        return
    if (warning := stale_checkout(ROOT)) is not None:
        log(f"warning: {warning}")
    chosen = config.group(group)
    repos = discover(config, group)[group]
    if repo is not None:
        repos = [r for r in repos if r.name in repo]
    plan = planned_runs(config, chosen, repos, load_state(), prompt or [])
    summary = ", ".join(f"{r.name} {p.name}" for r, p in plan)
    log(f"group {group}: {summary or 'nothing due'}")
    if dry_run or not plan:
        return

    results = run_plan(config, group, plan)
    log("summary: " + "; ".join(results))
    notify(f"{APP_NAME}: {group}", "; ".join(results))


@app.command()
def cleanup(
    *,
    scheduled: Annotated[
        bool,
        typer.Option(hidden=True, help="Started by launchd."),
    ] = False,
) -> None:
    """Remove checkouts whose pull requests are merged or closed."""
    if scheduled and is_weekend(load_config()):
        log("skipping cleanup, since it is the weekend")
        return
    cleanup_pending()


@app.command(name="list")
def list_groups() -> None:
    """Show which repositories fall into which group, and their prompts."""
    for name, repos in discover(load_config()).items():
        typer.echo(f"{name}:" + ("" if repos else " -"))
        for repo in repos:
            typer.echo(f"  {repo.name} ({', '.join(repo.prompts)})")


@app.command()
def status() -> None:
    """Show the schedule and the pull requests still pending."""
    config = load_config()
    loaded = set(installed_labels())
    for group in config.groups:
        mark = (
            "loaded" if config.launchd_label(group.name) in loaded else "NOT INSTALLED"
        )
        typer.echo(f"{group.name:<10} {group.weekday:<10} {group.time:%H:%M}  {mark}")
        for prompt in config.prompts:
            typer.echo(f"  {prompt.name}: {group.cadence_for(prompt)}")
    if config.skip_weekends:
        typer.echo("scheduled jobs skip Saturdays and Sundays")
    if (warning := stale_checkout(ROOT)) is not None:
        typer.secho(f"warning: {warning}", fg="yellow")
    state = load_state()
    typer.echo(f"\npending pull requests: {len(state.pending)}")
    for entry in state.pending:
        typer.echo(f"  {entry.pr_url}")
    if state.managed_clones:
        typer.echo("clones to delete after their PRs finish:")
        for path in state.managed_clones:
            typer.echo(f"  {path}")


@app.command()
def dashboard(
    *,
    open_browser: Annotated[
        bool,
        typer.Option("--open/--no-open", help="Open it in the browser."),
    ] = True,
) -> None:
    """Build an HTML dashboard of past runs and their pull requests from the logs."""
    DASHBOARD_FILE.write_text(render_dashboard(load_config()))
    typer.echo(f"wrote {DASHBOARD_FILE}")
    if open_browser:
        typer.launch(DASHBOARD_FILE.as_uri())


@app.command()
def install() -> None:
    """Build the app, then write and load the launchd agents."""
    config = load_config()
    install_agents(config)
    if not full_disk_access_granted(config):
        show_full_disk_access_steps()
    status()


@app.command()
def uninstall() -> None:
    """Unload and remove the launchd agents."""
    for label in installed_labels():
        unload(label)
        log(f"removed {label}")


@app.command()
def setup() -> None:
    """Interactive first-time setup, safe to rerun.

    Checks prerequisites and sign-ins, chooses private repositories, and
    installs the git hooks, the launchd agents, and Full Disk Access.
    """
    if not os.isatty(0):
        fail("setup is interactive; run it from a terminal")
    run_setup(load_config())
    step("Done")
    status()
    typer.echo("\nPreview a group with `make dry-run GROUP=<group>`.")
