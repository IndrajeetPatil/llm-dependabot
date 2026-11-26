"""Plan which prompts are due, and run the agent for each of them."""

import datetime as dt
import os
import signal
import subprocess
from typing import TYPE_CHECKING

lazy import filelock

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

if TYPE_CHECKING:
    from pathlib import Path

    from llm_dependabot.config import Agent, Config, Group, Prompt
    from llm_dependabot.github import PullRequest, Repo
    from llm_dependabot.state import Checkout, State


def planned_runs(
    config: Config, group: Group, repos: list[Repo], state: State, forced: list[str]
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
    agent: Agent, worktree: Path, prompt: str, log_path: Path, timeout_hours: float
) -> int:
    """Run the agent in a worktree, logging its output; return its exit code.

    A run that outlasts its timeout is stopped and returns -1.
    """
    argv, via_stdin = agent.argv(prompt, timeout_hours)
    with log_path.open("w") as out:
        proc = subprocess.Popen(
            argv,
            cwd=worktree,
            stdin=subprocess.PIPE if via_stdin else subprocess.DEVNULL,
            stdout=out,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            text=True,
        )
        try:
            # Agents with a timeout of their own stop first; this stops the rest.
            proc.communicate(
                prompt if via_stdin else None, timeout=timeout_hours * 3600 + 600
            )
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait()
            return -1
        return proc.wait()


def agent_pass(
    checkout: Checkout, repo: Repo, prompt: Prompt, config: Config, label: str
) -> tuple[int, PullRequest | None]:
    """Run the agent in a prepared checkout, then find the pull request it opened."""
    # The prompt is passed verbatim, exactly as committed in the repository.
    text = (checkout.worktree / prompt.path).read_text()
    log(f"{label}: running agent in {checkout.worktree} (log: {checkout.log})")
    code = run_agent(
        config.agent,
        checkout.worktree,
        text,
        checkout.log,
        config.agent_timeout_hours,
    )
    log(f"{label}: agent exited with code {code}")
    current = sh(
        "git", "-C", checkout.worktree, "branch", "--show-current", check=False
    )
    checkout.final_branch = current or checkout.branch
    return code, find_pr(repo, checkout.final_branch, checkout.started)


def process_repo(
    repo: Repo, prompt: Prompt, config: Config, state: State, run_dir: Path
) -> str:
    """Run one prompt in one repository; return a one-line summary."""
    label = f"{repo.name} {prompt.name}"
    log_path = run_dir / f"{repo.name}-{prompt.name}.log"
    checkout = prepare_checkout(repo, prompt, config, state, log_path)
    try:
        code, pr = agent_pass(checkout, repo, prompt, config, label)
    except Exception:
        remove_checkout(checkout)
        raise

    if pr is None:
        log(f"{label}: no pull request was opened; removing the worktree")
        remove_checkout(checkout)
        return f"{label}: no PR (exit {code})"

    log(f"{label}: {pr.state.lower()} pull request {pr.url}")
    state.pending.append(
        Pending(**checkout.model_dump(), pr_number=pr.number, pr_url=pr.url)
    )
    save_state(state)
    if config.label is not None:
        try:
            add_label(repo, pr.number, config.label)
        except subprocess.CalledProcessError as exc:
            log(f"{label}: cannot label {pr.url}: {exc.stderr}")
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
    return results


def cleanup() -> None:
    """Clean up after finished pull requests, unless a run holds the lock."""
    try:
        with filelock.FileLock(LOCK_FILE, timeout=0):
            cleanup_finished(load_state())
    except filelock.Timeout:
        log("a run is in progress; skipping cleanup")
