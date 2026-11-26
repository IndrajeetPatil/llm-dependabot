"""Plan which prompts are due, and run the agent for each of them."""

import datetime as dt
import os
import signal
import subprocess
import threading
from contextlib import contextmanager
from typing import TYPE_CHECKING

import filelock

from llm_dependabot.checkouts import (
    SkipRepoError,
    cleanup_finished,
    prepare_checkout,
    remove_checkout,
)
from llm_dependabot.github import add_label, find_pr
from llm_dependabot.paths import LOCK_FILE, LOG_DIR
from llm_dependabot.shell import log, sh
from llm_dependabot.state import Pending, load_state, save_state

# How often to look for the run's pull request while the agent works.
LABEL_POLL_SECONDS = 180

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from llm_dependabot.config import Agent, Config, Group, Prompt, PullRequestLabel
    from llm_dependabot.github import PullRequest, Repo
    from llm_dependabot.state import Checkout, State


def planned_runs(
    config: Config,
    group: Group,
    repos: list[Repo],
    state: State,
    forced: list[str],
) -> list[tuple[Repo, Prompt]]:
    """The (repository, prompt) pairs to run, in order.

    Prompts named with --prompt always run; otherwise each prompt runs when
    its cadence makes it due.
    """
    prompts = [config.prompt(name) for name in forced] or config.prompts
    return [
        (repo, prompt)
        for repo in repos
        for prompt in prompts
        if prompt.name in repo.prompts
        and (forced or state.is_due(prompt, repo, group.cadence_for(prompt)))
    ]


def run_agent(
    agent: Agent,
    worktree: Path,
    prompt: str,
    log_path: Path,
    timeout_hours: float,
) -> int:
    """Run the agent in a worktree, logging its output; return its exit code.

    A run that outlasts its timeout is stopped and returns -1.
    """
    argv, via_stdin = agent.argv(prompt, timeout_hours)
    with log_path.open("w", encoding="utf-8") as out:
        proc = subprocess.Popen(
            argv,
            cwd=worktree,
            stdin=subprocess.PIPE if via_stdin else subprocess.DEVNULL,
            stdout=out,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            encoding="utf-8",
        )
        try:
            # Agents with a timeout of their own stop first; this stops the rest.
            proc.communicate(
                prompt if via_stdin else None,
                timeout=timeout_hours * 3600 + 600,
            )
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait()
            return -1
        return proc.wait()


def current_branch(checkout: Checkout) -> str:
    """The branch checked out in the worktree, which the agent may have changed."""
    current = sh(
        "git",
        "-C",
        checkout.worktree,
        "branch",
        "--show-current",
        check=False,
    )
    return current or checkout.branch


def label_pr(
    repo: Repo,
    pr: PullRequest,
    pr_label: PullRequestLabel,
    label: str,
) -> bool:
    """Label a pull request; return whether that worked, logging why not."""
    try:
        add_label(repo, pr.number, pr_label)
    except subprocess.CalledProcessError as exc:
        log(f"{label}: cannot label {pr.url}: {exc.stderr}")
        return False
    return True


@contextmanager
def labelling_early(
    checkout: Checkout,
    repo: Repo,
    pr_label: PullRequestLabel | None,
    label: str,
) -> Generator[set[int]]:
    """While the agent works, label its pull request as soon as one exists.

    Agents often keep working for hours after opening the pull request, for
    example while they wait for CI and review. Yields the numbers of the pull
    requests labelled so far, so the check after the agent exits can skip them.
    """
    labelled: set[int] = set()
    if pr_label is None:
        yield labelled
        return
    stop = threading.Event()

    def watch(pr_label: PullRequestLabel) -> None:
        while not stop.wait(LABEL_POLL_SECONDS):
            try:
                pr = find_pr(repo, current_branch(checkout), checkout.started)
            except Exception as exc:  # ruff: ignore[blind-except] (retry at the next poll)
                log(f"{label}: cannot look for the pull request yet: {exc}")
                continue
            if pr is not None and label_pr(repo, pr, pr_label, label):
                labelled.add(pr.number)
                log(f"{label}: labelled {pr.url}")
                return

    watcher = threading.Thread(target=watch, args=(pr_label,), daemon=True)
    watcher.start()
    try:
        yield labelled
    finally:
        stop.set()
        watcher.join()


def agent_pass(
    checkout: Checkout,
    repo: Repo,
    prompt: Prompt,
    config: Config,
    label: str,
) -> tuple[int, PullRequest | None, set[int]]:
    """Run the agent in a prepared checkout, then find the pull request it opened.

    Also returns the pull requests labelled while the agent ran.
    """
    # The prompt is passed verbatim, exactly as committed in the repository.
    text = (checkout.worktree / prompt.path).read_text()
    log(f"{label}: running agent in {checkout.worktree} (log: {checkout.log})")
    with labelling_early(checkout, repo, config.label, label) as labelled:
        code = run_agent(
            config.agent,
            checkout.worktree,
            text,
            checkout.log,
            config.agent_timeout_hours,
        )
    log(f"{label}: agent exited with code {code}")
    checkout.final_branch = current_branch(checkout)
    pr = find_pr(repo, checkout.final_branch, checkout.started)
    return code, pr, labelled


def process_repo(
    repo: Repo,
    prompt: Prompt,
    config: Config,
    state: State,
    run_dir: Path,
) -> str:
    """Run one prompt in one repository; return a one-line summary."""
    label = f"{repo.name} {prompt.name}"
    log_path = run_dir / f"{repo.name}-{prompt.name}.log"
    checkout = prepare_checkout(repo, prompt, config, state, log_path)
    try:
        code, pr, labelled = agent_pass(checkout, repo, prompt, config, label)
    except Exception:
        remove_checkout(checkout)
        raise

    if pr is None:
        log(f"{label}: no pull request was opened; removing the worktree")
        remove_checkout(checkout)
        return f"{label}: no PR (exit {code})"

    log(f"{label}: {pr.state.lower()} pull request {pr.url}")
    state.pending.append(
        Pending(**checkout.model_dump(), pr_number=pr.number, pr_url=pr.url),
    )
    save_state(state)
    if config.label is not None and pr.number not in labelled:
        label_pr(repo, pr, config.label, label)
    return f"{label}: PR #{pr.number}"


def run_plan(config: Config, group: str, plan: list[tuple[Repo, Prompt]]) -> list[str]:
    """Run each planned prompt in turn, then clean up; return one-line summaries."""
    with filelock.FileLock(LOCK_FILE):
        # Keep the Mac awake (idle sleep) for as long as this process runs.
        caffeinate = subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])
        run_dir = LOG_DIR / f"{dt.datetime.now():%Y-%m-%d-%H%M}-{group}"
        run_dir.mkdir(parents=True, exist_ok=True)
        state = load_state()
        results = []
        for item, task in plan:
            label = f"{item.name} {task.name}"
            try:
                results.append(process_repo(item, task, config, state, run_dir))
                state.record_run(task, item)
            except SkipRepoError as exc:
                log(f"{label}: skipped: {exc}")
                results.append(f"{label}: skipped")
            except Exception as exc:  # ruff: ignore[blind-except] (keep going with the other repos)
                detail = getattr(exc, "stderr", "") or exc
                log(f"{label}: failed: {detail}")
                results.append(f"{label}: failed")
        cleanup_finished(state)
        caffeinate.terminate()
        # Reap it, so it does not linger as a zombie until this process exits.
        caffeinate.wait()
    return results


def cleanup() -> None:
    """Clean up after finished pull requests, unless a run holds the lock."""
    try:
        with filelock.FileLock(LOCK_FILE, timeout=0):
            cleanup_finished(load_state())
    except filelock.Timeout:
        log("a run is in progress; skipping cleanup")
