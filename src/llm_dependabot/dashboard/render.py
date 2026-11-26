"""Render past runs, totals, and the schedule as a self-contained HTML page."""

import datetime as dt
from importlib.resources import files
from typing import TYPE_CHECKING
lazy import html

from llm_dependabot.config import WEEKDAYS
from llm_dependabot.dashboard.runs import collect_runs
from llm_dependabot.paths import LOG_DIR

if TYPE_CHECKING:
    from llm_dependabot.config import Config, Group
    from llm_dependabot.dashboard.runs import GroupRun, Job

TEMPLATES = files("llm_dependabot.dashboard") / "templates"


def template(name: str) -> str:
    """The text of a file in the dashboard's templates folder."""
    return (TEMPLATES / name).read_text()


def next_run(group: Group, now: dt.datetime) -> dt.datetime:
    """When launchd next starts the group's run after now."""
    days = (WEEKDAYS.index(group.weekday) - now.isoweekday()) % 7
    when = dt.datetime.combine(now.date() + dt.timedelta(days=days), group.time)
    return when if when > now else when + dt.timedelta(weeks=1)


def format_duration(start: dt.datetime, end: dt.datetime | None) -> str:
    """A short, human-readable duration, or a dash if unfinished."""
    if end is None:
        return "&ndash;"
    minutes, seconds = divmod(int((end - start).total_seconds()), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours} h {minutes:02} min"
    return f"{minutes} min" if minutes else f"{seconds} s"


def job_status(job: Job, final: dict[str, str]) -> tuple[str, str]:
    """A job's outcome as a (CSS class, text) chip."""
    if job.pr_url is not None:
        state = final.get(job.pr_url, job.pr_state or "open")
        return state, state
    if job.problem is not None and job.problem.startswith("failed"):
        return "failed", "failed"
    if job.exit_code not in {0, None}:
        return "failed", f"exit {job.exit_code}"
    if job.problem is not None:
        return "muted", job.problem.partition(":")[0]
    return "muted", "unknown" if job.finished else "running"


def render_job(job: Job, owner: str, final: dict[str, str]) -> str:
    """A table row for one job."""
    esc = html.escape
    kind, text = job_status(job, final)
    status = f'<span class="chip {kind}">{esc(text)}</span>'
    if job.pr_url is not None:
        number = job.pr_url.rpartition("/")[2]
        status = f'<a href="{esc(job.pr_url)}">#{number}</a> {status}'
    transcript = (
        f'<a href="{esc(job.transcript.as_uri())}">log</a>'
        if job.transcript and job.transcript.exists()
        else ""
    )
    exit_code = "" if job.exit_code is None else str(job.exit_code)
    search = esc(f"{job.repo} {job.prompt} {text}".lower())
    repo_url = f"https://github.com/{owner}/{job.repo}"
    return (
        f'<tr data-search="{search}">'
        f'<th scope="row"><a href="{esc(repo_url)}">{esc(job.repo)}</a></th>'
        f"<td>{esc(job.prompt) or '&ndash;'}</td>"
        f"<td>{job.started:%H:%M}</td>"
        f'<td class="num">{format_duration(job.started, job.finished)}</td>'
        f'<td class="num{" bad" if exit_code not in {"", "0"} else ""}">'
        f"{exit_code}</td>"
        f"<td>{status}</td><td>{transcript}</td></tr>"
    )


def render_run(run: GroupRun, owner: str, final: dict[str, str]) -> str:
    """A section for one group run, with a table of its jobs."""
    esc = html.escape
    end = f"&ndash;{run.finished:%H:%M}" if run.finished else ""
    title = (
        f'<span class="when">{run.started:%a %d %b %Y, %H:%M}{end}</span>'
        f'<span class="group">{esc(run.group)}</span>'
    )
    note = f'<p class="note">{esc(run.note)}</p>' if run.note is not None else ""
    if not run.jobs:
        return f'<section class="run empty"><h3>{title}</h3>{note}</section>'
    rows = "".join(render_job(job, owner, final) for job in run.jobs)
    meta = (
        f"{len(run.jobs)} job{'s' * (len(run.jobs) != 1)}"
        f" · {format_duration(run.started, run.finished)}"
    )
    return (
        f'<section class="run"><h3>{title}<span class="meta">{meta}</span></h3>'
        f'{note}<div class="table-wrapper"><table>'
        "<thead><tr><th>Repository</th><th>Prompt</th><th>Started</th>"
        '<th class="num">Took</th><th class="num">Exit</th><th>Pull request</th>'
        f"<th>Transcript</th></tr></thead><tbody>{rows}</tbody></table></div>"
        "</section>"
    )


def render_dashboard(config: Config) -> str:
    """The complete dashboard page."""
    esc = html.escape
    now = dt.datetime.now()
    runs, final = collect_runs(config)
    jobs = [job for run in runs for job in run.jobs]
    statuses = [job_status(job, final)[0] for job in jobs]
    tiles = [
        ("Group runs", sum(1 for run in runs if run.jobs)),
        ("Agent runs", len(jobs)),
        ("Pull requests", sum(1 for job in jobs if job.pr_url is not None)),
        ("Merged", statuses.count("merged")),
        ("Open", statuses.count("open")),
        ("Failed", statuses.count("failed")),
    ]
    stats = "".join(
        f'<div class="tile"><span class="value">{value}</span>'
        f'<span class="label">{name}</span></div>'
        for name, value in tiles
    )
    schedule = "".join(
        f"<tr><th scope='row'>{esc(group.name)}</th>"
        f"<td>{group.weekday[:3]} {group.time:%H:%M}</td>"
        f"<td>{next_run(group, now):%a %d %b, %H:%M}</td><td>"
        + ", ".join(
            f"{esc(p.name)} <span class='muted'>{group.cadence_for(p)}</span>"
            for p in config.prompts
        )
        + "</td></tr>"
        for group in sorted(config.groups, key=lambda g: next_run(g, now))
    )
    body = "".join(render_run(run, config.owner, final) for run in runs) or (
        f'<p class="note">No runs logged in {esc(str(LOG_DIR))} yet.</p>'
    )
    weekend = " Scheduled jobs skip weekends." if config.skip_weekends else ""
    return template("page.html").format(
        css=template("style.css"),
        theme=template("theme.js"),
        script=template("script.js"),
        generated=f"{now:%a %d %b %Y, %H:%M}",
        stats=stats,
        schedule=schedule,
        weekend=weekend,
        runs=body,
    )
