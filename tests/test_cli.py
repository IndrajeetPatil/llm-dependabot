"""Tests for the Typer commands, with discovery and runs faked."""

import datetime as dt
import runpy
import sys
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from llm_dependabot import __version__, cli
from llm_dependabot.cli import app
from llm_dependabot.state import Checkout, Pending, State, save_state

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from llm_dependabot.config import Config
    from llm_dependabot.github import Repo

runner = CliRunner()

pytestmark: pytest.MarkDecorator = pytest.mark.usefixtures("use_config")


@pytest.fixture
def use_config(config: Config, monkeypatch: pytest.MonkeyPatch) -> None:
    """Use the test config and report no installed agents."""
    monkeypatch.setattr(cli, "load_config", lambda: config)
    monkeypatch.setattr(cli, "installed_labels", list)


@pytest.fixture
def discovered(monkeypatch: pytest.MonkeyPatch, make_repo: Callable[..., Repo]) -> None:
    """Fake discovery with two python repositories."""
    grouped = {
        "python": [make_repo("app", "update-deps"), make_repo("lib", "update-deps")],
        "rest": [],
    }
    monkeypatch.setattr(cli, "discover", lambda _config, _group=None: grouped)


def fail_if_called(*_args: object) -> list[str]:
    """Fail the test; stands in for what must not run."""
    pytest.fail("a dry run must not run anything")


@pytest.mark.usefixtures("discovered")
def test_a_dry_run_lists_what_would_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """A dry run logs the plan and runs nothing."""
    monkeypatch.setattr(cli, "run_plan", fail_if_called)
    result = runner.invoke(app, ["run", "python", "--dry-run", "--repo", "lib"])
    assert result.exit_code == 0, result.output
    assert "group python: lib update-deps" in result.output


@pytest.mark.usefixtures("discovered")
def test_a_run_runs_the_plan_and_notifies(monkeypatch: pytest.MonkeyPatch) -> None:
    """A run logs and notifies its summary."""
    notified: list[tuple[str, str]] = []
    monkeypatch.setattr(
        cli,
        "run_plan",
        lambda _c, _g, plan: [f"{r.name}: PR #1" for r, _ in plan],
    )
    monkeypatch.setattr(cli, "notify", lambda *args: notified.append(args))
    result = runner.invoke(app, ["run", "python"])
    assert result.exit_code == 0, result.output
    assert "summary: app: PR #1; lib: PR #1" in result.output
    assert notified == [("LLM Dependabot: python", "app: PR #1; lib: PR #1")]


def test_a_scheduled_run_skips_weekends(monkeypatch: pytest.MonkeyPatch) -> None:
    """A scheduled run on a weekend does nothing."""
    monkeypatch.setattr(cli, "is_weekend", lambda _config: True)
    monkeypatch.setattr(cli, "discover", fail_if_called)
    result = runner.invoke(app, ["run", "python", "--scheduled"])
    assert result.exit_code == 0, result.output
    assert "skipped, since it is the weekend" in result.output


def test_an_unknown_group_fails() -> None:
    """An unknown group fails with the choices."""
    result = runner.invoke(app, ["run", "nope"])
    assert result.exit_code == 1
    assert "unknown group 'nope'" in result.output


@pytest.mark.usefixtures("discovered")
def test_list_shows_each_group() -> None:
    """The list command prints each group with its repositories and prompts."""
    result = runner.invoke(app, ["list"])
    assert (
        result.output == "python:\n  app (update-deps)\n  lib (update-deps)\nrest: -\n"
    )


def test_status_shows_the_schedule_and_pending_pull_requests(home: Path) -> None:
    """The status command prints the schedule, cadences, and pending pull requests."""
    save_state(
        State(
            pending=[
                Pending(
                    repo="octo/app",
                    clone=home / "app",
                    worktree=home / "wt",
                    branch="b",
                    log=home / "l",
                    started=dt.datetime(2026, 11, 24, 10, tzinfo=dt.UTC),
                    pr_number=1,
                    pr_url="https://github.com/octo/app/pull/1",
                ),
            ],
        ),
    )
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0, result.output
    assert "python     Tuesday    11:00  NOT INSTALLED" in result.output
    assert "  update-deps: monthly" in result.output  # the rest group's override
    assert (
        "pending pull requests: 1\n  https://github.com/octo/app/pull/1"
        in result.output
    )


@pytest.mark.parametrize("flag", ["--version", "-V"])
def test_version(flag: str) -> None:
    """The version flag prints the version and exits."""
    result = runner.invoke(app, [flag])
    assert result.exit_code == 0
    assert result.output == f"llm-dependabot {__version__}\n"


def test_python_dash_m_runs_the_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    """Python -m llm_dependabot runs the same app."""
    monkeypatch.setattr(sys, "argv", ["llm_dependabot", "--version"])
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("llm_dependabot", run_name="__main__")
    assert exit_info.value.code == 0


@pytest.mark.parametrize(
    ("args", "weekend", "cleans"),
    [
        pytest.param([], True, True, id="by hand, even at weekends"),
        pytest.param(["--scheduled"], False, True, id="scheduled on a weekday"),
        pytest.param(["--scheduled"], True, False, id="scheduled at the weekend"),
    ],
)
def test_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    args: list[str],
    *,
    weekend: bool,
    cleans: bool,
) -> None:
    """Cleanup runs by hand any day, but a scheduled one skips weekends."""
    cleaned: list[bool] = []
    monkeypatch.setattr(cli, "is_weekend", lambda _config: weekend)
    monkeypatch.setattr(cli, "cleanup_pending", lambda: cleaned.append(True))
    result = runner.invoke(app, ["cleanup", *args])
    assert result.exit_code == 0, result.output
    assert cleaned == ([True] if cleans else [])


def test_status_lists_clones_awaiting_deletion(home: Path) -> None:
    """Clones this tool made are listed until their pull requests finish."""
    save_state(State(managed_clones=[home / "clones/app"]))
    result = runner.invoke(app, ["status"])
    assert f"clones to delete after their PRs finish:\n  {home / 'clones/app'}" in (
        result.output
    )


@pytest.mark.parametrize(
    ("args", "opened"),
    [
        pytest.param([], True, id="opens by default"),
        pytest.param(["--no-open"], False, id="--no-open"),
    ],
)
def test_dashboard_writes_the_page(
    monkeypatch: pytest.MonkeyPatch,
    args: list[str],
    *,
    opened: bool,
) -> None:
    """The dashboard command writes the page, and opens it unless told not to."""
    launched: list[str] = []
    monkeypatch.setattr(cli, "render_dashboard", lambda _config: "<!doctype html>")
    monkeypatch.setattr(cli.typer, "launch", launched.append)
    result = runner.invoke(app, ["dashboard", *args])
    assert result.exit_code == 0, result.output
    assert cli.DASHBOARD_FILE.read_text() == "<!doctype html>"
    assert launched == ([cli.DASHBOARD_FILE.as_uri()] if opened else [])


@pytest.mark.parametrize("granted", [True, False])
def test_install(monkeypatch: pytest.MonkeyPatch, *, granted: bool) -> None:
    """Install loads the agents, then shows the access steps if still needed."""
    calls: list[str] = []
    monkeypatch.setattr(cli, "install_agents", lambda _config: calls.append("install"))
    monkeypatch.setattr(cli, "full_disk_access_granted", lambda _config: granted)
    monkeypatch.setattr(
        cli,
        "show_full_disk_access_steps",
        lambda: calls.append("steps"),
    )
    result = runner.invoke(app, ["install"])
    assert result.exit_code == 0, result.output
    assert calls == (["install"] if granted else ["install", "steps"])
    assert "pending pull requests: 0" in result.output


def test_uninstall_removes_every_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Uninstall unloads each installed agent."""
    labels = ["com.example.llm-dependabot.python"]
    unloaded: list[str] = []
    monkeypatch.setattr(cli, "installed_labels", lambda: labels)
    monkeypatch.setattr(cli, "unload", unloaded.append)
    result = runner.invoke(app, ["uninstall"])
    assert result.exit_code == 0, result.output
    assert unloaded == labels
    assert f"removed {labels[0]}" in result.output


@pytest.mark.parametrize("terminal", [True, False])
def test_setup_needs_a_terminal(
    monkeypatch: pytest.MonkeyPatch,
    *,
    terminal: bool,
) -> None:
    """Setup runs its steps from a terminal, and refuses to run without one."""
    ran: list[Config] = []
    monkeypatch.setattr(cli.os, "isatty", lambda _fd: terminal)
    monkeypatch.setattr(cli, "run_setup", ran.append)
    result = runner.invoke(app, ["setup"])
    assert result.exit_code == (0 if terminal else 1)
    assert len(ran) == (1 if terminal else 0)
    assert ("make dry-run" in result.output) is terminal


@pytest.mark.parametrize("skip_weekends", [True, False])
def test_status_mentions_skipped_weekends_only_when_on(
    config: Config,
    *,
    skip_weekends: bool,
) -> None:
    """The weekend note appears only when scheduled jobs skip weekends."""
    config.skip_weekends = skip_weekends
    config.groups = [
        g for g in config.groups if g.weekday not in {"Saturday", "Sunday"}
    ]
    result = runner.invoke(app, ["status"])
    assert ("skip Saturdays and Sundays" in result.output) is skip_weekends


@pytest.mark.parametrize(
    "args",
    [
        pytest.param(["status"], id="status"),
        pytest.param(["run", "python", "--dry-run"], id="run"),
    ],
)
@pytest.mark.usefixtures("discovered")
def test_stale_checkout_warnings_are_shown(
    monkeypatch: pytest.MonkeyPatch,
    args: list[str],
) -> None:
    """Runs and status warn when the tool's own checkout misses merged code."""
    monkeypatch.setattr(cli, "stale_checkout", lambda _root: "it is behind")
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "warning: it is behind" in result.output


def test_status_lists_checkouts_retained_for_recovery(home: Path) -> None:
    """Recovery paths and transcripts are visible without inspecting the state file."""
    checkout = Checkout(
        repo="octo/project",
        clone=home / "clone",
        worktree=home / "wt",
        branch="agent/work",
        log=home / "agent.log",
        started=dt.datetime(2026, 11, 26, tzinfo=dt.UTC),
    )
    save_state(State(recovery=[checkout]))
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0, result.output
    assert "checkouts retained for manual recovery:" in result.output
    assert f"octo/project: {checkout.worktree} (log: {checkout.log})" in result.output
