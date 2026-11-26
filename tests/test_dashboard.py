"""Tests for reading runs back from the logs and rendering the dashboard."""

import datetime as dt
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, override

import pytest

from llm_dependabot.config import Prompt
from llm_dependabot.dashboard import render, runs
from llm_dependabot.dashboard.render import (
    format_duration,
    job_status,
    next_run,
    render_dashboard,
)
from llm_dependabot.dashboard.runs import (
    GroupRun,
    Job,
    collect_runs,
    parse_group_log,
    read_log,
)
from llm_dependabot.state import Pending, State, save_state

if TYPE_CHECKING:
    from collections.abc import Callable

    from llm_dependabot.config import Config
    from tests.conftest import Spy


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
        "[2026-12-08 11:00:00] group python: app update-deps\n",
    )
    (log_dir / "cleanup.log").write_text(
        "[2026-11-25 08:00:00] octo/app#12 is merged; cleaning up\n",
    )
    return run_dir


def test_read_log_skips_untimestamped_lines() -> None:
    """Lines without a timestamp, such as shell noise, are skipped."""
    write_run(runs.LOG_DIR)
    lines = read_log(runs.LOG_DIR / "python.log")
    assert lines[0] == (AT, "group python: app update-deps, lib update-deps")
    assert len(lines) == 8


def test_read_log_replaces_undecodable_bytes(spy: Callable[[Any, str], Spy]) -> None:
    """Logs are read as UTF-8, and a stray byte does not stop the dashboard."""
    log = runs.LOG_DIR / "python.log"
    log.parent.mkdir(parents=True)
    log.write_bytes(b"[2026-11-24 11:00:00] caf\xc3\xa9 \xff\n")
    read_text = spy(Path, "read_text")
    assert read_log(log) == [(AT, "caf\u00e9 \ufffd")]
    assert read_text.calls == [((log,), {"encoding": "utf-8", "errors": "replace"})]


def test_parse_group_log() -> None:
    """A group log splits into runs and their jobs."""
    run_dir = write_run(runs.LOG_DIR)
    first, nothing, unfinished = parse_group_log(
        "python",
        read_log(runs.LOG_DIR / "python.log"),
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


def test_parse_group_log_ignores_lines_before_the_first_run() -> None:
    """Events and summaries logged outside a run belong to no run."""
    lines = [
        "summary: app: PR #1",
        "app update-deps: running agent in /wt/app (log: /logs/run/app.log)",
        "group python: skipped, since it is the weekend",
        "summary: app: PR #1",
        "app update-deps: agent exited with code 0",
    ]
    [run] = parse_group_log("python", [(AT, line) for line in lines])
    assert run.note == "skipped, since it is the weekend"
    assert run.finished == AT
    assert run.jobs == []


def test_collect_runs_reads_final_pull_request_states(
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    config: Config,
) -> None:
    """Cleanup logs and pending state give each pull request's final state."""
    write_run(runs.LOG_DIR)
    (runs.LOG_DIR / "rest.log").write_text(
        "[2026-11-25 09:30:00] group rest: nothing due\n",
    )
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
                ),
            ],
        ),
    )
    collected, final = collect_runs(config)
    assert [run.started for run in collected] == sorted(
        (run.started for run in collected),
        reverse=True,
    )
    assert [(run.group, run.note) for run in collected] == [
        ("python", "interrupted before its summary"),
        ("python", "nothing due"),
        ("rest", "nothing due"),
        ("python", None),
    ]
    assert final == {
        "https://github.com/octo/app/pull/12": "merged",
        "https://github.com/octo/lib/pull/3": "open",
    }


@pytest.mark.parametrize(
    ("running", "notes"),
    [
        pytest.param(
            [],
            ["interrupted before its summary", "interrupted before its summary"],
            id="no job running",
        ),
        pytest.param(
            ["com.example.llm-dependabot.python"],
            [None, "interrupted before its summary"],
            id="the group running",
        ),
    ],
)
def test_only_the_latest_run_of_a_running_group_is_in_progress(
    monkeypatch: pytest.MonkeyPatch,
    config: Config,
    running: list[str],
    notes: list[str | None],
) -> None:
    """An unfinished run was interrupted, unless it is its group's running one."""
    runs.LOG_DIR.mkdir(parents=True)
    (runs.LOG_DIR / "python.log").write_text(
        "[2026-11-24 11:00:00] group python: app update-deps\n"
        "[2026-11-24 11:05:00] summary: app update-deps: PR #1\n"
        "[2026-12-01 11:00:00] group python: app update-deps\n"
        "[2026-12-08 11:00:00] group python: app update-deps\n",
    )
    monkeypatch.setattr(runs, "running_jobs", lambda: running)
    collected, _ = collect_runs(config)
    assert [run.note for run in collected] == [*notes, None]


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
            local("2026-11-24 10:59"),
            local("2026-11-24 11:00"),
            id="later today",
        ),
        pytest.param(
            local("2026-11-24 11:00"),
            local("2026-12-01 11:00"),
            id="just started",
        ),
        pytest.param(
            local("2026-11-29 23:00"),
            local("2026-12-01 11:00"),
            id="later this week",
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


@pytest.mark.parametrize(
    ("lines", "expected"),
    [
        pytest.param(
            [
                "group python: app",
                "app: running agent in /wt/app (log: /logs/run/app.log)",
                "app: no pull request was opened; removing the worktree",
            ],
            "no pull request",
            id="no pull request",
        ),
        pytest.param(
            ["group python: app", "app: skipped: busy"],
            "skipped: busy",
            id="skipped before starting",
        ),
        pytest.param(
            ["group python: app", "other: agent exited with code 0"],
            None,
            id="event for a job that never started",
        ),
    ],
)
def test_job_problems(lines: list[str], expected: str | None) -> None:
    """Jobs record why they ended without a PR; stray events are ignored."""
    [run] = parse_group_log("python", [(AT, line) for line in lines])
    assert [job.problem for job in run.jobs] == ([] if expected is None else [expected])
    assert [(job.repo, job.prompt) for job in run.jobs] == (
        [] if expected is None else [("app", "")]
    )


@pytest.mark.parametrize(
    ("event", "transcript"),
    [
        pytest.param(
            "running agent in /wt/app (log: /logs/run/app.log)",
            "run/app.log",
            id="absolute log",
        ),
        pytest.param(
            "running agent in /wt/app (log: app.log)",
            None,
            id="log without a folder",
        ),
        pytest.param(
            "running agent in /wt/a (log: x)/b (log: /logs/run/app.log)",
            "run/app.log",
            id="worktree mentioning a log",
        ),
        pytest.param(
            "running agent in /wt/a (log: x)/b (log: app.log)",
            None,
            id="worktree mentioning a log, log without a folder",
        ),
    ],
)
def test_transcripts_are_found_in_the_log_directory(
    event: str,
    transcript: str | None,
) -> None:
    """A transcript is the last logged path, resolved in the log directory."""
    [run] = parse_group_log(
        "python",
        [(AT, "group python: app"), (AT, f"app update-deps: {event}")],
    )
    [job] = run.jobs
    assert job.transcript == (None if transcript is None else runs.LOG_DIR / transcript)


def test_collect_runs_without_any_logs(
    monkeypatch: pytest.MonkeyPatch,
    config: Config,
) -> None:
    """Before the first run there is no log directory, and so no runs."""
    monkeypatch.setattr(runs, "running_jobs", list)
    assert collect_runs(config) == ([], {})


def test_runs_started_by_hand_are_read_from_their_transcripts(
    monkeypatch: pytest.MonkeyPatch,
    config: Config,
) -> None:
    """A run folder no group log mentions becomes a run of its transcripts.

    macOS reports when each transcript was created and Linux does not, so the
    test sets the creation time, on either system, to a minute before each
    modification.
    """
    real_stat = Path.stat

    def stat(path: Path, *, follow_symlinks: bool = True) -> SimpleNamespace:
        """The real stat result, with the birth time set or replaced."""
        result = real_stat(path, follow_symlinks=follow_symlinks)
        fields = {
            name: getattr(result, name)
            for name in dir(result)
            if name.startswith("st_")
        }
        fields["st_birthtime"] = result.st_mtime - 60
        return SimpleNamespace(**fields)

    monkeypatch.setattr(Path, "stat", stat)
    monkeypatch.setattr(runs, "running_jobs", list)
    # Prompts whose names end alike: the longest matching name wins.
    config.prompts.extend(
        Prompt(name=name, path=f".github/prompts/{name}.md")
        for name in ("deps", "a-deps")
    )
    folder = runs.LOG_DIR / "2026-11-24-0915-rest"
    folder.mkdir(parents=True)
    for name in ("app-simplify-codebase", "lib-unknown", "tool-a-deps"):
        (folder / f"{name}.log").write_text("transcript\n")
    (runs.LOG_DIR / "1-not-a-run").mkdir()
    (runs.LOG_DIR / "2026-11-24-0915-loose.txt").write_text("")
    (runs.LOG_DIR / "2026-11-25-0915-empty").mkdir()

    empty, run = collect_runs(config)[0]
    assert (empty.group, empty.jobs, empty.finished) == ("empty", [], None)
    assert (run.group, run.started) == ("rest", local("2026-11-24 09:15"))
    assert run.note == "started by hand; outcomes are not logged"
    jobs = {(job.repo, job.prompt, job.transcript) for job in run.jobs}
    assert jobs == {
        ("app", "simplify-codebase", folder / "app-simplify-codebase.log"),
        ("lib-unknown", "", folder / "lib-unknown.log"),
        ("tool", "a-deps", folder / "tool-a-deps.log"),
    }
    finished = [job.finished for job in run.jobs if job.finished is not None]
    assert len(finished) == len(run.jobs)
    assert {end - job.started for end, job in zip(finished, run.jobs, strict=True)} == {
        dt.timedelta(minutes=1),
    }
    assert run.finished == max(finished)


PAGE = (
    "css={css}\ntheme={theme}\nscript={script}\ngenerated={generated}\n"
    "stats={stats}\nschedule={schedule}\nweekend={weekend}\nruns={runs}"
)


class FixedClock(dt.datetime):
    """A datetime whose now is Monday 23 November 2026, 08:00."""

    @override
    @classmethod
    def now(cls, tz: dt.tzinfo | None = None) -> FixedClock:
        """Monday 23 November 2026, 08:00."""
        return cls(2026, 11, 23, 8)


@pytest.fixture
def page(monkeypatch: pytest.MonkeyPatch) -> Callable[..., str]:
    """Render the dashboard of the given runs, with stub templates and a fixed clock."""
    monkeypatch.setattr(
        render,
        "template",
        lambda name: PAGE if name == "page.html" else f"<{name}>",
    )
    monkeypatch.setattr(
        render,
        "dt",
        SimpleNamespace(datetime=FixedClock, timedelta=dt.timedelta),
    )

    def make(
        config: Config,
        collected: list[GroupRun],
        final: dict[str, str],
    ) -> str:
        """The page for these runs and final pull request states."""
        monkeypatch.setattr(render, "collect_runs", lambda _config: (collected, final))
        return render_dashboard(config)

    return make


def job(**fields: object) -> Job:
    """A job of octo's app, started at AT, with these fields."""
    return Job.model_validate({"repo": "app", "prompt": "p", "started": AT, **fields})


def test_render_dashboard_page(
    page: Callable[..., str],
    config: Config,
    tmp_path: Path,
) -> None:
    """Every part of the page renders exactly."""
    transcript = tmp_path / "app.log"
    transcript.write_text("transcript\n")
    pr = "https://github.com/octo/app/pull/12"
    collected = [
        GroupRun(
            group="<python>",
            started=AT,
            finished=AT + dt.timedelta(minutes=65),
            jobs=[
                job(
                    finished=AT + dt.timedelta(minutes=20, seconds=5),
                    exit_code=0,
                    pr_url=pr,
                    pr_state="open",
                    transcript=transcript,
                ),
                job(repo="lib", prompt="", problem="skipped: busy: retry later"),
                job(repo="Tool", exit_code=0, finished=AT, problem="no pull request"),
                job(repo="web", exit_code=2, transcript=tmp_path / "missing.log"),
            ],
        ),
        GroupRun(
            group="rest",
            started=AT,
            note="started by hand",
            jobs=[job(pr_url="https://github.com/octo/app/pull/13")],
        ),
        GroupRun(group="rest", started=AT, finished=AT, note="nothing due"),
    ]
    uri = transcript.as_uri()
    assert page(config, collected, {pr: "merged"}) == (
        "css=<style.css>"
        "\ntheme=<theme.js>"
        "\nscript=<script.js>"
        "\ngenerated=Mon 23 Nov 2026, 08:00"
        "\nstats="
        '<div class="tile"><span class="value">2</span>'
        '<span class="label">Group runs</span></div>'
        '<div class="tile"><span class="value">5</span>'
        '<span class="label">Agent runs</span></div>'
        '<div class="tile"><span class="value">2</span>'
        '<span class="label">Pull requests</span></div>'
        '<div class="tile"><span class="value">1</span>'
        '<span class="label">Merged</span></div>'
        '<div class="tile"><span class="value">1</span>'
        '<span class="label">Open</span></div>'
        '<div class="tile"><span class="value">1</span>'
        '<span class="label">Failed</span></div>'
        "\nschedule="
        "<tr><th scope='row'>python</th><td>Tue 11:00</td>"
        "<td>Tue 24 Nov, 11:00</td><td>update-deps "
        "<span class='muted'>weekly</span>, simplify-codebase "
        "<span class='muted'>monthly</span></td></tr>"
        "<tr><th scope='row'>rest</th><td>Wed 09:30</td>"
        "<td>Wed 25 Nov, 09:30</td><td>update-deps "
        "<span class='muted'>monthly</span>, simplify-codebase "
        "<span class='muted'>monthly</span></td></tr>"
        "\nweekend= Scheduled jobs skip weekends."
        "\nruns="
        '<section class="run"><h3>'
        '<span class="when">Tue 24 Nov 2026, 11:00&ndash;12:05</span>'
        '<span class="group">&lt;python&gt;</span>'
        '<span class="meta">4 jobs · 1 h 05 min</span></h3>'
        '<div class="table-wrapper"><table><thead>'
        "<tr><th>Repository</th><th>Prompt</th><th>Started</th>"
        '<th class="num">Took</th><th class="num">Exit</th>'
        "<th>Pull request</th><th>Transcript</th></tr></thead><tbody>"
        '<tr data-search="app p merged"><th scope="row">'
        '<a href="https://github.com/octo/app">app</a></th><td>p</td>'
        '<td>11:00</td><td class="num">20 min</td><td class="num">0</td>'
        '<td><a href="https://github.com/octo/app/pull/12">#12</a> '
        '<span class="chip merged">merged</span></td><td>'
        f'<a href="{uri}">log</a></td></tr>'
        '<tr data-search="lib  skipped"><th scope="row">'
        '<a href="https://github.com/octo/lib">lib</a></th><td>&ndash;'
        '</td><td>11:00</td><td class="num">&ndash;</td><td class="num">'
        '</td><td><span class="chip muted">skipped</span></td><td></td>'
        "</tr>"
        '<tr data-search="tool p no pull request"><th scope="row">'
        '<a href="https://github.com/octo/Tool">Tool</a></th><td>p</td>'
        '<td>11:00</td><td class="num">0 s</td><td class="num">0</td><td>'
        '<span class="chip muted">no pull request</span></td><td></td></tr>'
        '<tr data-search="web p exit 2"><th scope="row">'
        '<a href="https://github.com/octo/web">web</a></th><td>p</td>'
        '<td>11:00</td><td class="num">&ndash;</td><td class="num bad">2'
        '</td><td><span class="chip failed">exit 2</span></td><td></td>'
        "</tr></tbody></table></div></section>"
        '<section class="run"><h3>'
        '<span class="when">Tue 24 Nov 2026, 11:00</span>'
        '<span class="group">rest</span><span class="meta">1 job · &ndash;'
        '</span></h3><p class="note">started by hand</p>'
        '<div class="table-wrapper"><table><thead>'
        "<tr><th>Repository</th><th>Prompt</th><th>Started</th>"
        '<th class="num">Took</th><th class="num">Exit</th>'
        "<th>Pull request</th><th>Transcript</th></tr></thead><tbody>"
        '<tr data-search="app p open"><th scope="row">'
        '<a href="https://github.com/octo/app">app</a></th><td>p</td>'
        '<td>11:00</td><td class="num">&ndash;</td><td class="num"></td>'
        '<td><a href="https://github.com/octo/app/pull/13">#13</a> '
        '<span class="chip open">open</span></td><td></td></tr></tbody>'
        "</table></div></section>"
        '<section class="run empty"><h3>'
        '<span class="when">Tue 24 Nov 2026, 11:00&ndash;11:00</span>'
        '<span class="group">rest</span></h3><p class="note">nothing due'
        "</p></section>"
    )


@pytest.mark.parametrize(
    ("skip_weekends", "weekend"),
    [
        pytest.param(True, " Scheduled jobs skip weekends.", id="skipped"),
        pytest.param(False, "", id="run"),
    ],
)
def test_render_dashboard_without_runs(
    page: Callable[..., str],
    config: Config,
    *,
    skip_weekends: bool,
    weekend: str,
) -> None:
    """Without runs, the page says where it looked; weekends are noted if skipped."""
    config.skip_weekends = skip_weekends
    rendered = page(config, [], {})
    assert f"\nweekend={weekend}\n" in rendered
    assert rendered.endswith(
        f'runs=<p class="note">No runs logged in {runs.LOG_DIR} yet.</p>',
    )
