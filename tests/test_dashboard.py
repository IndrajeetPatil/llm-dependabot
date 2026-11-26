"""Tests for reading runs back from the logs and rendering the dashboard."""

import datetime as dt
from typing import TYPE_CHECKING

import pytest

from llm_dependabot.dashboard import render, runs
from llm_dependabot.dashboard.render import (
    format_duration,
    job_status,
    next_run,
    render_dashboard,
)
from llm_dependabot.dashboard.runs import Job, collect_runs, parse_group_log, read_log
from llm_dependabot.state import Pending, State, save_state

if TYPE_CHECKING:
    from pathlib import Path

    from llm_dependabot.config import Config


def local(text: str) -> dt.datetime:
    """A naive local time, as the logs record them."""
    return dt.datetime.fromisoformat(text)


AT: dt.datetime = local("2026-11-24 11:00")


def write_run(log_dir: Path) -> Path:
    """A python group log with one PR, one failure, and a run that found nothing."""
    run_dir = log_dir / "2026-11-24-1100-python"
    run_dir.mkdir(parents=True)
    (run_dir / "app-update-deps.log").write_text("transcript\n")
    (log_dir / "python.log").write_text(
        "zsh: noise from the login shell\n"
        "[2026-11-24 11:00:00] group python: app update-deps, lib update-deps\n"
        "[2026-11-24 11:00:05] app update-deps: running agent in /wt/app"
        f" (log: {run_dir}/app-update-deps.log)\n"
        "[2026-11-24 11:20:05] app update-deps: agent exited with code 0\n"
        "[2026-11-24 11:20:09] app update-deps: open pull request"
        " https://github.com/octo/app/pull/12\n"
        "[2026-11-24 11:20:10] lib update-deps: failed: fetch failed\n"
        "[2026-11-24 11:20:11] summary: app update-deps: PR #12; lib: failed\n"
        "[2026-12-01 11:00:00] group python: nothing due\n"
        "[2026-12-08 11:00:00] group python: app update-deps\n"
    )
    (log_dir / "cleanup.log").write_text(
        "[2026-11-25 08:00:00] octo/app#12 is merged; cleaning up\n"
    )
    return run_dir


def test_read_log_skips_untimestamped_lines() -> None:
    """Lines without a timestamp, such as shell noise, are skipped."""
    write_run(runs.LOG_DIR)
    lines = read_log(runs.LOG_DIR / "python.log")
    assert lines[0] == (AT, "group python: app update-deps, lib update-deps")
    assert len(lines) == 8


def test_parse_group_log() -> None:
    """A group log splits into runs and their jobs."""
    run_dir = write_run(runs.LOG_DIR)
    first, nothing, unfinished = parse_group_log(
        "python", read_log(runs.LOG_DIR / "python.log")
    )
    assert first.finished == local("2026-11-24 11:20:11")
    app, lib = first.jobs
    assert (app.repo, app.prompt, app.exit_code) == ("app", "update-deps", 0)
    assert app.pr_url == "https://github.com/octo/app/pull/12"
    assert app.pr_state == "open"
    assert app.transcript == run_dir / "app-update-deps.log"
    assert lib.problem == "failed: fetch failed"
    assert lib.transcript is None
    assert nothing.note == "nothing due"
    assert unfinished.finished is None


def test_collect_runs_reads_final_pull_request_states(
    home: Path, monkeypatch: pytest.MonkeyPatch, config: Config
) -> None:
    """Cleanup logs and pending state give each pull request's final state."""
    write_run(runs.LOG_DIR)
    monkeypatch.setattr(runs, "running_jobs", list)
    save_state(
        State(
            pending=[
                Pending(
                    repo="octo/lib",
                    clone=home / "lib",
                    worktree=home / "wt",
                    branch="b",
                    log=home / "l",
                    started=AT.astimezone(dt.UTC),
                    pr_number=3,
                    pr_url="https://github.com/octo/lib/pull/3",
                )
            ]
        )
    )
    collected, final = collect_runs(config)
    assert [run.started for run in collected] == sorted(
        (run.started for run in collected), reverse=True
    )
    assert collected[0].note == "interrupted before its summary"
    assert final == {
        "https://github.com/octo/app/pull/12": "merged",
        "https://github.com/octo/lib/pull/3": "open",
    }


@pytest.mark.parametrize(
    ("fields", "status"),
    [
        pytest.param({"pr_url": "u/1"}, ("merged", "merged"), id="merged since"),
        pytest.param({"pr_url": "u/2"}, ("open", "open"), id="still open"),
        pytest.param({"problem": "failed: x"}, ("failed", "failed"), id="failed"),
        pytest.param({"exit_code": 2}, ("failed", "exit 2"), id="non-zero exit"),
        pytest.param({"problem": "skipped: busy"}, ("muted", "skipped"), id="skipped"),
        pytest.param({}, ("muted", "running"), id="running"),
        pytest.param({"finished": AT}, ("muted", "unknown"), id="finished, no outcome"),
    ],
)
def test_job_status(fields: dict[str, object], status: tuple[str, str]) -> None:
    """Each job outcome maps to its chip, using the final state of its pull request."""
    job = Job.model_validate({"repo": "a", "prompt": "p", "started": AT, **fields})
    assert job_status(job, {"u/1": "merged"}) == status


@pytest.mark.parametrize(
    ("minutes", "text"),
    [
        pytest.param(0.5, "30 s", id="seconds"),
        pytest.param(12, "12 min", id="minutes"),
        pytest.param(65, "1 h 05 min", id="hours"),
        pytest.param(None, "&ndash;", id="unfinished"),
    ],
)
def test_format_duration(minutes: float | None, text: str) -> None:
    """Durations are shown in the largest sensible unit, or a dash if unfinished."""
    end = None if minutes is None else AT + dt.timedelta(minutes=minutes)
    assert format_duration(AT, end) == text


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        # Tuesday 24 November 2026; the python group runs on Tuesdays at 11:00.
        pytest.param(
            local("2026-11-24 10:59"), local("2026-11-24 11:00"), id="later today"
        ),
        pytest.param(
            local("2026-11-24 11:00"), local("2026-12-01 11:00"), id="just started"
        ),
        pytest.param(
            local("2026-11-29 23:00"), local("2026-12-01 11:00"), id="later this week"
        ),
    ],
)
def test_next_run(config: Config, now: dt.datetime, expected: dt.datetime) -> None:
    """The next run is the group's next weekday and time after now."""
    assert next_run(config.group("python"), now) == expected


def test_render_dashboard(monkeypatch: pytest.MonkeyPatch, config: Config) -> None:
    """The page fills every placeholder and escapes configured names."""
    write_run(runs.LOG_DIR)
    monkeypatch.setattr(runs, "running_jobs", list)
    config.groups[0] = config.groups[0].model_copy(update={"name": "<python>"})
    page = render_dashboard(config)
    assert page.startswith("<!doctype html>")
    names = ("css", "theme", "script", "stats", "schedule", "runs")
    placeholders = [f"{{{name}}}" for name in names]
    assert not any(placeholder in page for placeholder in placeholders)
    assert "&lt;python&gt;" in page
    assert '<a href="https://github.com/octo/app/pull/12">#12</a>' in page
    assert '<span class="chip merged">merged</span>' in page
    assert render.template("style.css") in page
