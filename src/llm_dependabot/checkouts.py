"""Worktrees for agent runs, and their cleanup once pull requests finish."""

import datetime as dt
import shutil
import subprocess
from typing import TYPE_CHECKING

from llm_dependabot.github import FINISHED_PR_STATES, pr_state
from llm_dependabot.paths import WORKTREE_ROOT
from llm_dependabot.shell import log, sh
from llm_dependabot.state import Checkout, save_state

if TYPE_CHECKING:
    from pathlib import Path

    from llm_dependabot.config import Config, Prompt
    from llm_dependabot.github import Repo
    from llm_dependabot.state import State


class SkipRepoError(Exception):
    """A repository cannot be processed this run."""


def remote_matches(clone: Path, repo: Repo) -> bool:
    """Whether the clone's origin is the repository on GitHub."""
    url = sh("git", "-C", clone, "remote", "get-url", "origin", check=False)
    return url.lower().removesuffix(".git").endswith(repo.full_name.lower())


def prepare_checkout(
    repo: Repo, prompt: Prompt, config: Config, state: State, log_path: Path
) -> Checkout:
    """Create a worktree on a fresh branch off the default branch.

    The agent works in a separate worktree so an existing clone's checked-out
    branch and uncommitted work are never touched.
    """
    clone = config.clone_root / repo.name
    if (clone / ".git").exists():
        if not remote_matches(clone, repo):
            msg = f"{clone} is a clone of a different repository"
            raise SkipRepoError(msg)
    elif clone.exists():
        msg = f"{clone} exists but is not a git clone"
        raise SkipRepoError(msg)
    else:
        log(f"{repo.name}: no local copy, cloning into {clone}")
        sh("gh", "repo", "clone", repo.full_name, clone, "--", "--quiet")
        state.managed_clones.append(clone)
        save_state(state)

    sh("git", "-C", clone, "fetch", "--prune", "--quiet", "origin")
    started = dt.datetime.now(dt.UTC).replace(microsecond=0)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    checkout = Checkout(
        repo=repo.full_name,
        clone=clone,
        worktree=WORKTREE_ROOT / f"{repo.name}-{prompt.name}-{stamp}",
        branch=f"chore/{prompt.name}-{stamp}",
        log=log_path,
        started=started,
    )
    WORKTREE_ROOT.mkdir(parents=True, exist_ok=True)
    sh(
        "git",
        "-C",
        clone,
        "worktree",
        "add",
        "--quiet",
        "--no-track",
        "-b",
        checkout.branch,
        checkout.worktree,
        f"origin/{repo.default_branch}",
    )
    return checkout


def remove_checkout(checkout: Checkout) -> None:
    """Remove a checkout's worktree and its local branches, if the clone remains."""
    clone = checkout.clone
    if not clone.exists():
        return
    if checkout.worktree.exists():
        sh("git", "-C", clone, "worktree", "remove", "--force", checkout.worktree,
           check=False)  # fmt: skip
    sh("git", "-C", clone, "worktree", "prune", check=False)
    for branch in {checkout.branch, checkout.final_branch or checkout.branch}:
        sh("git", "-C", clone, "branch", "-D", branch, check=False)


def clone_is_disposable(clone: Path) -> tuple[bool, str]:
    """Whether a clone holds no local work; if not, a reason saying why."""
    if sh("git", "-C", clone, "status", "--porcelain", check=False):
        return False, "has uncommitted changes"
    worktrees = sh("git", "-C", clone, "worktree", "list", "--porcelain", check=False)
    if worktrees.count("worktree ") > 1:
        return False, "has other worktrees"
    if sh("git", "-C", clone, "log", "--branches", "--not", "--remotes", "--oneline",
          check=False):  # fmt: skip
        return False, "has local commits that are not on the remote"
    return True, ""


def delete_unused_managed_clones(state: State) -> None:
    """Delete clones this tool created once no pending pull request needs them."""
    in_use = {entry.clone for entry in state.pending}
    kept = []
    for clone in state.managed_clones:
        if clone in in_use:
            kept.append(clone)
            continue
        if not clone.exists():
            continue
        disposable, reason = clone_is_disposable(clone)
        if disposable:
            log(f"deleting {clone}: it did not exist before its agent run")
            shutil.rmtree(clone)
        else:
            log(f"keeping {clone} for now: it {reason}")
            kept.append(clone)
    state.managed_clones = kept
    save_state(state)


def cleanup_finished(state: State) -> None:
    """Remove checkouts whose pull requests finished, then unused clones."""
    remaining = []
    for entry in state.pending:
        pr_ref = f"{entry.repo}#{entry.pr_number}"
        try:
            current = pr_state(entry.repo, entry.pr_number)
        except subprocess.CalledProcessError as exc:
            log(f"{pr_ref}: cannot check state: {exc.stderr}")
            remaining.append(entry)
            continue
        if current in FINISHED_PR_STATES:
            log(f"{pr_ref} is {current.lower()}; cleaning up")
            remove_checkout(entry)
        else:
            remaining.append(entry)
    state.pending = remaining
    save_state(state)
    delete_unused_managed_clones(state)
