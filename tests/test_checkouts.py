"""Checkouts against real git repositories, with a local bare repository as origin."""

import datetime as dt
import shutil
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
    stale_checkout,
)
from llm_dependabot.state import Checkout, Pending, State, load_state

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from llm_dependabot.config import Config
    from llm_dependabot.github import Repo


def git(*args: str | Path) -> str:
    """Run git with a fixed identity and return its output."""
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
    clone: Path,
    config: Config,
    make_repo: Callable[..., Repo],
    tmp_path: Path,
) -> None:
    """A run works in its own worktree and leaves the clone alone."""
    git("-C", clone, "checkout", "--quiet", "-b", "my-work")
    (clone / "notes.txt").write_text("uncommitted\n")
    prompt = config.prompt("update-deps")
    checkout = prepare_checkout(
        make_repo(),
        prompt,
        config,
        State(),
        tmp_path / "a.log",
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


def foreign_clone(project: Path) -> None:
    """Make the project directory a clone of another repository."""
    git("init", "--quiet", project)
    git("-C", project, "remote", "add", "origin", "https://example.com/x/y.git")


def plain_directory(project: Path) -> None:
    """Make the project directory an ordinary directory."""
    project.mkdir(parents=True)


@pytest.mark.parametrize(
    ("occupy", "match"),
    [
        pytest.param(foreign_clone, "different repository", id="foreign clone"),
        pytest.param(plain_directory, "not a git clone", id="plain directory"),
    ],
)
def test_a_directory_in_the_way_is_skipped(
    config: Config,
    make_repo: Callable[..., Repo],
    tmp_path: Path,
    occupy: Callable[[Path], None],
    match: str,
) -> None:
    """Anything in the clone's place other than its own clone is left alone."""
    occupy(config.clone_root / "project")
    with pytest.raises(SkipRepoError, match=match):
        prepare_checkout(
            make_repo(),
            config.prompt("update-deps"),
            config,
            State(),
            tmp_path / "l",
        )


def leave_clean(_clone: Path) -> None:
    """Change nothing."""


def edit_a_file(clone: Path) -> None:
    """Leave an uncommitted change."""
    (clone / "README.md").write_text("changed\n")


def commit_locally(clone: Path) -> None:
    """Commit a change that is not pushed."""
    edit_a_file(clone)
    git("-C", clone, "commit", "--quiet", "-am", "local")


def add_a_worktree(clone: Path) -> None:
    """Add a worktree of the clone's own."""
    git("-C", clone, "worktree", "add", "--quiet", "--detach", clone.parent / "wt")


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        pytest.param(leave_clean, (True, ""), id="clean"),
        pytest.param(edit_a_file, (False, "has uncommitted changes"), id="edited"),
        pytest.param(
            commit_locally,
            (False, "has local commits that are not on the remote"),
            id="unpushed commit",
        ),
        pytest.param(add_a_worktree, (False, "has other worktrees"), id="worktree"),
    ],
)
def test_clone_is_disposable(
    clone: Path,
    change: Callable[[Path], None],
    expected: tuple[bool, str],
) -> None:
    """Only a clean clone without local commits or other worktrees may be deleted."""
    change(clone)
    assert clone_is_disposable(clone) == expected


def test_cleanup_removes_finished_pull_requests_and_their_managed_clones(
    clone: Path,
    config: Config,
    make_repo: Callable[..., Repo],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Cleanup keeps open pull requests and deletes clones nothing needs."""
    state = State(managed_clones=[clone])
    checkout = prepare_checkout(
        make_repo(),
        config.prompt("update-deps"),
        config,
        state,
        tmp_path / "l",
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


def test_a_missing_clone_is_cloned_and_managed(
    clone: Path,
    config: Config,
    make_repo: Callable[..., Repo],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Without a local copy, gh clones one, and cleanup may later delete it."""
    origin = tmp_path / "remote/octo/project.git"
    shutil.rmtree(clone)
    real_sh = checkouts.sh

    def sh(*args: str | Path, check: bool = True) -> str:
        """Clone from the local origin where gh would clone from GitHub."""
        if args[:3] == ("gh", "repo", "clone"):
            return real_sh("git", "clone", "--quiet", origin, args[4])
        return real_sh(*args, check=check)

    monkeypatch.setattr(checkouts, "sh", sh)
    state = State()
    checkout = prepare_checkout(
        make_repo(),
        config.prompt("update-deps"),
        config,
        state,
        tmp_path / "l",
    )
    assert (checkout.worktree / "README.md").exists()
    assert state.managed_clones == [clone]
    assert load_state().managed_clones == [clone]


def test_removing_a_checkout_of_a_deleted_clone_does_nothing(tmp_path: Path) -> None:
    """A checkout whose clone the user deleted is simply forgotten."""
    gone = tmp_path / "gone"
    remove_checkout(
        Checkout(
            repo="octo/project",
            clone=gone,
            worktree=gone / "wt",
            branch="b",
            log=tmp_path / "l",
            started=dt.datetime(2026, 11, 26, tzinfo=dt.UTC),
        ),
    )
    assert not gone.exists()


def test_cleanup_keeps_what_it_cannot_safely_remove(
    clone: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Unknown PR states and clones with local work survive; vanished clones go."""
    (clone / "README.md").write_text("local work\n")
    vanished = tmp_path / "vanished"
    elsewhere = tmp_path / "elsewhere"
    pending = Pending(
        repo="octo/project",
        clone=elsewhere,
        worktree=elsewhere / "wt",
        branch="b",
        log=tmp_path / "l",
        started=dt.datetime(2026, 11, 26, tzinfo=dt.UTC),
        pr_number=1,
        pr_url="u/1",
    )
    state = State(pending=[pending], managed_clones=[vanished, clone])

    def pr_state(_repo: str, _number: int) -> str:
        """Fail like gh does when GitHub cannot be reached."""
        raise subprocess.CalledProcessError(1, "gh", stderr="offline")

    monkeypatch.setattr(checkouts, "pr_state", pr_state)
    cleanup_finished(state)
    assert load_state().pending == [pending]
    assert load_state().managed_clones == [clone]
    out = capsys.readouterr().out
    assert "octo/project#1: cannot check state: offline" in out
    assert f"keeping {clone} for now: it has uncommitted changes" in out


def stay_current(_clone: Path) -> None:
    """Leave the clone on main, level with origin."""


def switch_branch(clone: Path) -> None:
    """Check out a feature branch."""
    git("-C", clone, "switch", "--quiet", "-c", "feat/x")


def detach(clone: Path) -> None:
    """Detach HEAD at the current commit."""
    git("-C", clone, "switch", "--quiet", "--detach")


def fall_behind(clone: Path) -> None:
    """Push a commit to origin, then step the local main back before it."""
    git("-C", clone, "commit", "--quiet", "--allow-empty", "-m", "merged")
    git("-C", clone, "push", "--quiet", "origin", "HEAD:main")
    git("-C", clone, "reset", "--quiet", "--hard", "HEAD~1")


def follow_origin_head(clone: Path) -> None:
    """Record origin's default branch, as a fresh clone of a non-empty repo does."""
    git("-C", clone, "fetch", "--quiet", "origin")
    git("-C", clone, "remote", "set-head", "origin", "main")


@pytest.mark.parametrize(
    ("arrange", "expected"),
    [
        pytest.param(stay_current, None, id="current"),
        pytest.param(follow_origin_head, None, id="current with origin/HEAD"),
        pytest.param(switch_branch, "has feat/x checked out, not main", id="branch"),
        pytest.param(detach, "has a detached HEAD checked out", id="detached"),
        pytest.param(fall_behind, "is 1 commit(s) behind origin/main", id="behind"),
    ],
)
def test_stale_checkout_flags_code_scheduled_runs_would_miss(
    clone: Path,
    arrange: Callable[[Path], None],
    expected: str | None,
) -> None:
    """The tool's checkout is flagged when off the default branch or behind it."""
    arrange(clone)
    warning = stale_checkout(clone)
    if expected is None:
        assert warning is None
    else:
        assert warning is not None
        assert expected in warning


def test_stale_checkout_ignores_a_directory_that_is_not_a_clone(
    tmp_path: Path,
) -> None:
    """Outside a git checkout, such as an unpacked copy, there is nothing to check."""
    assert stale_checkout(tmp_path) is None
