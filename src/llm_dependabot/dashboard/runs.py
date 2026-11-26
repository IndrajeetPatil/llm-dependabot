"""Read past runs back from the group logs and the run transcripts."""

import datetime as dt
import re
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import Field

from llm_dependabot.config import Strict
from llm_dependabot.launchd import running_jobs
from llm_dependabot.paths import LOG_DIR
from llm_dependabot.state import load_state

if TYPE_CHECKING:
    from llm_dependabot.config import Config

LOG_LINE = re.compile(r"\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\] (.*)")
RUN_FOLDER = re.compile(r"(\d{4}-\d\d-\d\d)-(\d\d)(\d\d)-(.+)")
PR_EVENT = re.compile(r"(open|merged|closed) pull request (https://\S+/pull/\d+)")
PR_FINISHED = re.compile(r"(\S+/\S+)#(\d+) is (merged|closed); cleaning up")
EXIT_EVENT = re.compile(r"agent exited with code (-?\d+)")


class Job(Strict):
    """One prompt's agent run in one repository, as read back from the logs."""

    repo: str
    prompt: str
    started: dt.datetime
    finished: dt.datetime | None = None
    exit_code: int | None = None
    pr_url: str | None = None
    pr_state: str | None = None
    # Why the job ended without a pull request: skipped, failed, or none opened.
    problem: str | None = None
    transcript: Path | None = None


class GroupRun(Strict):
    """One run of a group, scheduled or started by hand."""

    group: str
    started: dt.datetime
    finished: dt.datetime | None = None
    note: str | None = None
    jobs: list[Job] = Field(default_factory=list)


def read_log(path: Path) -> list[tuple[dt.datetime, str]]:
    """The timestamped lines of a log, skipping noise from the login shell."""
    return [
        (dt.datetime.fromisoformat(match[1]), match[2])
        for line in path.read_text(errors="replace").splitlines()
        if (match := LOG_LINE.fullmatch(line))
    ]


def local_time(timestamp: float) -> dt.datetime:
    """A POSIX timestamp as a naive local time, like the log timestamps."""
    return (
        dt.datetime.fromtimestamp(timestamp, dt.UTC).astimezone().replace(tzinfo=None)
    )


def record_job_event(
    run: GroupRun,
    jobs: dict[str, Job],
    at: dt.datetime,
    label: str,
    event: str,
) -> None:
    # Labels are "<repo> <prompt>"; older logs carry only "<repo>".
    """Apply one logged event to the job it belongs to, creating it if new."""
    repo, _, prompt = label.partition(" ")
    problem = event.startswith(("skipped: ", "failed: "))
    if event.startswith("running agent in ") or (problem and label not in jobs):
        # Resolve the transcript in LOG_DIR, which may have moved since.
        logged = Path(event.rpartition("(log: ")[2].removesuffix(")"))
        jobs[label] = Job(
            repo=repo,
            prompt=prompt,
            started=at,
            transcript=LOG_DIR / logged.parent.name / logged.name
            if logged.parent.name
            else None,
        )
        run.jobs.append(jobs[label])
    job = jobs.get(label)
    if job is None:
        return
    if code := EXIT_EVENT.fullmatch(event):
        job.exit_code, job.finished = int(code[1]), at
    elif pr := PR_EVENT.fullmatch(event):
        job.pr_state, job.pr_url = pr[1], pr[2]
    elif event.startswith("no pull request"):
        job.problem = "no pull request"
    elif problem:
        job.problem, job.finished = event, at


def parse_group_log(group: str, lines: list[tuple[dt.datetime, str]]) -> list[GroupRun]:
    """Split a group log's lines into the runs they record."""
    runs: list[GroupRun] = []
    run: GroupRun | None = None
    jobs: dict[str, Job] = {}
    for at, message in lines:
        label, _, event = message.partition(": ")
        if label == f"group {group}":
            run = GroupRun(group=group, started=at)
            jobs = {}
            runs.append(run)
            if event == "nothing due" or event.startswith("skipped"):
                run.note, run.finished, run = event, at, None
        elif run is not None and label == "summary":
            run.finished, run = at, None
        elif run is not None:
            record_job_event(run, jobs, at, label, event)
    return runs


def manual_runs(config: Config, logged: set[Path]) -> list[GroupRun]:
    """Runs started by hand, which leave only their transcripts behind."""
    suffixes = sorted((f"-{p.name}" for p in config.prompts), key=len, reverse=True)
    runs = []
    for folder in LOG_DIR.iterdir():
        match = RUN_FOLDER.fullmatch(folder.name)
        if not folder.is_dir() or match is None or folder in logged:
            continue
        run = GroupRun(
            group=match[4],
            started=dt.datetime.fromisoformat(f"{match[1]} {match[2]}:{match[3]}"),
            note="started by hand; outcomes are not logged",
        )
        for transcript in folder.glob("*.log"):
            stem = transcript.stem
            suffix = next((s for s in suffixes if stem.endswith(s)), "")
            info = transcript.stat()
            run.jobs.append(
                Job(
                    repo=stem.removesuffix(suffix),
                    prompt=suffix.removeprefix("-"),
                    started=local_time(info.st_birthtime),
                    finished=local_time(info.st_mtime),
                    transcript=transcript,
                ),
            )
        run.jobs.sort(key=lambda j: j.started)
        run.finished = max((j.finished for j in run.jobs if j.finished), default=None)
        runs.append(run)
    return runs


def collect_runs(config: Config) -> tuple[list[GroupRun], dict[str, str]]:
    """Every run in the logs, newest first, and each PR's final state by URL."""
    runs: list[GroupRun] = []
    final: dict[str, str] = {}
    running = {label.rpartition(".")[2] for label in running_jobs()}
    for path in LOG_DIR.glob("*.log") if LOG_DIR.is_dir() else []:
        lines = read_log(path)
        for _, message in lines:
            if match := PR_FINISHED.fullmatch(message):
                final[f"https://github.com/{match[1]}/pull/{match[2]}"] = match[3]
        group_runs = parse_group_log(path.stem, lines)
        for run in group_runs:
            if run.finished is None and (
                run is not group_runs[-1] or run.group not in running
            ):
                run.note = "interrupted before its summary"
        runs += group_runs
    logged = {j.transcript.parent for r in runs for j in r.jobs if j.transcript}
    if LOG_DIR.is_dir():
        runs += manual_runs(config, logged)
    for entry in load_state().pending:
        final.setdefault(entry.pr_url, "open")
    return sorted(runs, key=lambda r: r.started, reverse=True), final
