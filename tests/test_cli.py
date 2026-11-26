import datetime as dt
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from llm_dependabot import cli
from llm_dependabot.cli import app
from llm_dependabot.state import Pending, State, save_state

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from llm_dependabot.config import Config
    from llm_dependabot.github import Repo

runner = CliRunner()


@pytest.fixture(autouse=True)
def use_config(config: Config, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "load_config", lambda: config)
    monkeypatch.setattr(cli, "installed_labels", list)


@pytest.fixture
def discovered(monkeypatch: pytest.MonkeyPatch, make_repo: Callable[..., Repo]) -> None:
    grouped = {
        "python": [make_repo("app", "update-deps"), make_repo("lib", "update-deps")],
        "rest": [],
    }
    monkeypatch.setattr(cli, "discover", lambda _config, _group=None: grouped)


def fail_if_called(*_args: object) -> list[str]:
    pytest.fail("a dry run must not run anything")


@pytest.mark.usefixtures("discovered")
def test_a_dry_run_lists_what_would_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "run_plan", fail_if_called)
    result = runner.invoke(app, ["run", "python", "--dry-run", "--repo", "lib"])
    assert result.exit_code == 0, result.output
    assert "group python: lib update-deps" in result.output


@pytest.mark.usefixtures("discovered")
def test_a_run_runs_the_plan_and_notifies(monkeypatch: pytest.MonkeyPatch) -> None:
    notified: list[tuple[str, str]] = []
    monkeypatch.setattr(
        cli, "run_plan", lambda _c, _g, plan: [f"{r.name}: PR #1" for r, _ in plan]
    )
    monkeypatch.setattr(cli, "notify", lambda *args: notified.append(args))
    result = runner.invoke(app, ["run", "python"])
    assert result.exit_code == 0, result.output
    assert "summary: app: PR #1; lib: PR #1" in result.output
    assert notified == [("LLM Dependabot: python", "app: PR #1; lib: PR #1")]


def test_a_scheduled_run_skips_weekends(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "is_weekend", lambda _config: True)
    monkeypatch.setattr(cli, "discover", fail_if_called)
    result = runner.invoke(app, ["run", "python", "--scheduled"])
    assert result.exit_code == 0, result.output
    assert "skipped, since it is the weekend" in result.output


def test_an_unknown_group_fails() -> None:
    result = runner.invoke(app, ["run", "nope"])
    assert result.exit_code == 1
    assert "unknown group 'nope'" in result.output


@pytest.mark.usefixtures("discovered")
def test_list_shows_each_group() -> None:
    result = runner.invoke(app, ["list"])
    assert (
        result.output == "python:\n  app (update-deps)\n  lib (update-deps)\nrest: -\n"
    )


def test_status_shows_the_schedule_and_pending_pull_requests(home: Path) -> None:
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
                )
            ],
        )
    )
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0, result.output
    assert "python     Tuesday    11:00  NOT INSTALLED" in result.output
    assert "  update-deps: monthly" in result.output  # the rest group's override
    assert (
        "pending pull requests: 1\n  https://github.com/octo/app/pull/1"
        in result.output
    )


def test_dashboard_writes_the_page(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "render_dashboard", lambda _config: "<!doctype html>")
    result = runner.invoke(app, ["dashboard", "--no-open"])
    assert result.exit_code == 0, result.output
    assert cli.DASHBOARD_FILE.read_text() == "<!doctype html>"
