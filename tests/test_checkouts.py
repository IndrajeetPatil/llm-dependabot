"""Checkouts against real git repositories, with a local bare repository as origin."""

import datetime as dt
import subprocess
from typing import TYPE_CHECKING

import pytest

from llm_dependabot import checkouts
from llm_dependabot.checkouts import (
    SkipRepoError,
    cleanup_finished,
    clone_is_disposable,
    prepare_checkout,
    remove_checkout,
)
from llm_dependabot.state import Pending, State, load_state

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from llm_dependabot.config import Config
    from llm_dependabot.github import Repo


def git(*args: str | Path) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def clone(tmp_path: Path, config: Config) -> Path:
    """A clone of octo/project, whose origin is a local bare repository."""
    origin = tmp_path / "remote/octo/project.git"
    git("init", "--quiet", "--bare", "--initial-branch=main", origin)
    clone = config.clone_root / "project"
    git("clone", "--quiet", origin, clone)
    (clone / "README.md").write_text("hello\n")
    git("-C", clone, "add", "README.md")
    git("-C", clone, "commit", "--quiet", "-m", "initial")
    git("-C", clone, "push", "--quiet", "origin", "HEAD:main")
    return clone


def test_prepare_checkout_adds_a_worktree_off_the_default_branch(
    clone: Path, config: Config, make_repo: Callable[..., Repo], tmp_path: Path
) -> None:
    git("-C", clone, "checkout", "--quiet", "-b", "my-work")
    (clone / "notes.txt").write_text("uncommitted\n")
    prompt = config.prompt("update-deps")
    checkout = prepare_checkout(
        make_repo(), prompt, config, State(), tmp_path / "a.log"
    )

    assert checkout.worktree.parent == checkouts.WORKTREE_ROOT
    assert checkout.branch.startswith("chore/update-deps-")
    assert (checkout.worktree / "README.md").read_text() == "hello\n"
    assert git("-C", checkout.worktree, "branch", "--show-current") == checkout.branch
    # The clone's own branch and uncommitted work are left alone.
    assert git("-C", clone, "branch", "--show-current") == "my-work"
    assert (clone / "notes.txt").exists()
    assert checkout.started.tzinfo is dt.UTC

    remove_checkout(checkout)
    assert not checkout.worktree.exists()
    assert checkout.branch not in git("-C", clone, "branch", "--list")


def test_a_clone_of_another_repository_is_skipped(
    clone: Path, config: Config, make_repo: Callable[..., Repo], tmp_path: Path
) -> None:
    git("-C", clone, "remote", "set-url", "origin", "https://example.com/x/y.git")
    with pytest.raises(SkipRepoError, match="different repository"):
        prepare_checkout(
            make_repo(), config.prompt("update-deps"), config, State(), tmp_path / "l"
        )


def test_a_directory_that_is_not_a_clone_is_skipped(
    config: Config, make_repo: Callable[..., Repo], tmp_path: Path
) -> None:
    (config.clone_root / "project").mkdir(parents=True)
    with pytest.raises(SkipRepoError, match="not a git clone"):
        prepare_checkout(
            make_repo(), config.prompt("update-deps"), config, State(), tmp_path / "l"
        )


def test_clone_is_disposable(clone: Path) -> None:
    assert clone_is_disposable(clone) == (True, "")
    (clone / "README.md").write_text("changed\n")
    assert clone_is_disposable(clone) == (False, "has uncommitted changes")
    git("-C", clone, "commit", "--quiet", "-am", "local")
    assert clone_is_disposable(clone) == (
        False,
        "has local commits that are not on the remote",
    )


def test_cleanup_removes_finished_pull_requests_and_their_managed_clones(
    clone: Path,
    config: Config,
    make_repo: Callable[..., Repo],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    state = State(managed_clones=[clone])
    checkout = prepare_checkout(
        make_repo(), config.prompt("update-deps"), config, state, tmp_path / "l"
    )
    # Two pull requests from one checkout: worktree names have minute precision.
    pending = [
        Pending(**checkout.model_dump(), pr_number=number, pr_url=f"u/{number}")
        for number in (1, 2)
    ]
    state.pending = pending
    states = {1: "OPEN", 2: "MERGED"}
    monkeypatch.setattr(checkouts, "pr_state", lambda _repo, number: states[number])

    cleanup_finished(state)
    assert [entry.pr_number for entry in load_state().pending] == [1]
    assert clone.exists()  # pull request 1 still needs it

    states[1] = "CLOSED"
    cleanup_finished(state)
    assert load_state().pending == []
    assert load_state().managed_clones == []
    assert not clone.exists()
