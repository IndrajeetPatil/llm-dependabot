"""Checkouts against real git repositories, with a local bare repository as origin."""

import datetime as dt
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, override

import pytest

from llm_dependabot import checkouts, runner
from llm_dependabot.checkouts import (
    SkipRepoError,
    cleanup_finished,
    clone_is_disposable,
    prepare_checkout,
    remove_checkout,
    stale_checkout,
)
from llm_dependabot.config import Prompt
from llm_dependabot.state import Checkout, Pending, State, load_state, save_state

if TYPE_CHECKING:
    from collections.abc import Callable

    from llm_dependabot.config import Config
    from llm_dependabot.github import Repo
    from tests.conftest import FakeCommands, Spy


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


class FixedClock(dt.datetime):
    """A datetime whose now is 26 November 2026, 10:30:15.5 local, 09:30 UTC."""

    @override
    @classmethod
    def now(cls, tz: dt.tzinfo | None = None) -> FixedClock:
        """The fixed time, in UTC if asked, else as naive local time."""
        if tz is None:
            return cls(2026, 11, 26, 10, 30, 15, 500000)
        return cls(2026, 11, 26, 9, 30, 15, 500000, tzinfo=tz)


def test_prepare_checkout_commands(
    clone: Path,
    config: Config,
    make_repo: Callable[..., Repo],
    monkeypatch: pytest.MonkeyPatch,
    spy: Callable[[Any, str], Spy],
) -> None:
    """The worktree is named after the local minute, and the start is in UTC.

    An existing worktree folder, from an earlier run, is reused.
    """
    monkeypatch.setattr(
        checkouts,
        "dt",
        SimpleNamespace(datetime=FixedClock, UTC=dt.UTC),
    )
    checkouts.WORKTREE_ROOT.mkdir(parents=True)
    sh = spy(checkouts, "sh")
    exists = spy(Path, "exists")
    log = clone.parent / "a.log"
    checkout = prepare_checkout(
        make_repo(),
        config.prompt("update-deps"),
        config,
        State(),
        log,
    )
    assert exists.calls[0] == ((clone / ".git",), {})
    worktree = checkouts.WORKTREE_ROOT / "project-update-deps-20261126-1030"
    assert checkout == Checkout(
        repo="octo/project",
        clone=clone,
        worktree=worktree,
        branch="chore/update-deps-20261126-1030",
        log=log,
        started=dt.datetime(2026, 11, 26, 9, 30, 15, tzinfo=dt.UTC),
    )
    assert [args for args, _ in sh.calls] == [
        ("git", "-C", clone, "remote", "get-url", "origin"),
        ("git", "-C", clone, "fetch", "--prune", "--quiet", "origin"),
        (
            "git",
            "-C",
            clone,
            "worktree",
            "add",
            "--quiet",
            "--no-track",
            "-b",
            "chore/update-deps-20261126-1030",
            worktree,
            "origin/main",
        ),
    ]
    assert [options for _, options in sh.calls] == [{"check": False}, {}, {}]


def test_remove_checkout_commands(
    clone: Path,
    spy: Callable[[Any, str], Spy],
    tmp_path: Path,
) -> None:
    """The worktree is forced out, then the run's and the agent's branches go."""
    worktree = tmp_path / "wt"
    git("-C", clone, "worktree", "add", "--quiet", "-b", "run", worktree)
    (worktree / "README.md").write_text("unsaved\n")
    git("-C", clone, "branch", "agent")
    git("-C", clone, "switch", "--quiet", "-c", "unmerged")
    git("-C", clone, "commit", "--quiet", "--allow-empty", "-m", "unmerged")
    git("-C", clone, "switch", "--quiet", "main")
    checkout = Checkout(
        repo="octo/project",
        clone=clone,
        worktree=worktree,
        branch="run",
        final_branch="unmerged",
        log=tmp_path / "l",
        started=dt.datetime(2026, 11, 26, tzinfo=dt.UTC),
    )
    sh = spy(checkouts, "sh")
    remove_checkout(checkout)
    assert not worktree.exists()
    assert git("-C", clone, "branch", "--format=%(refname:short)").split() == [
        "agent",
        "main",
    ]
    calls = [(args, options) for args, options in sh.calls]
    check = {"check": False}
    assert calls[:2] == [
        (("git", "-C", clone, "worktree", "remove", "--force", worktree), check),
        (("git", "-C", clone, "worktree", "prune"), check),
    ]
    assert sorted(calls[2:]) == [
        (("git", "-C", clone, "branch", "-D", "run"), check),
        (("git", "-C", clone, "branch", "-D", "unmerged"), check),
    ]


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


def test_clone_is_disposable_commands(
    clone: Path,
    spy: Callable[[Any, str], Spy],
) -> None:
    """Each check reads git's output, whatever its exit code."""
    sh = spy(checkouts, "sh")
    assert clone_is_disposable(clone) == (True, "")
    check = {"check": False}
    assert sh.calls == [
        (("git", "-C", clone, "status", "--porcelain"), check),
        (("git", "-C", clone, "worktree", "list", "--porcelain"), check),
        (
            (
                "git",
                "-C",
                clone,
                "log",
                "--branches",
                "--not",
                "--remotes",
                "--oneline",
            ),
            check,
        ),
    ]


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
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Without a local copy, gh clones one, and cleanup may later delete it."""
    origin = clone.parents[1] / "remote/octo/project.git"
    shutil.rmtree(clone)
    real_sh = checkouts.sh

    cloned: list[tuple[str | Path, ...]] = []

    def sh(*args: str | Path, check: bool = True) -> str:
        """Clone from the local origin where gh would clone from GitHub."""
        if args[0] == "gh":
            cloned.append(args)
            return real_sh("git", "clone", "--quiet", origin, args[4])
        return real_sh(*args, check=check)

    monkeypatch.setattr(checkouts, "sh", sh)
    state = State()
    checkout = prepare_checkout(
        make_repo(),
        config.prompt("update-deps"),
        config,
        state,
        clone.parent / "l",
    )
    assert (checkout.worktree / "README.md").exists()
    assert state.managed_clones == [clone]
    assert load_state().managed_clones == [clone]
    assert cloned == [("gh", "repo", "clone", "octo/project", clone, "--", "--quiet")]
    assert capsys.readouterr().out.endswith(
        f"] project: no local copy, cloning into {clone}\n",
    )


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


def test_cleanup_goes_through_every_entry(
    clone: Path,
    config: Config,
    make_repo: Callable[..., Repo],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A pull request or clone that must stay does not stop the rest's cleanup."""
    tmp_path = clone.parents[1]
    in_use = tmp_path / "in-use"
    vanished = tmp_path / "vanished"
    checkout = prepare_checkout(
        make_repo(),
        config.prompt("update-deps"),
        config,
        State(),
        tmp_path / "l",
    )
    entries = [
        Pending(**checkout.model_dump(), pr_number=number, pr_url=f"u/{number}")
        for number in (1, 2)
    ]
    entries[0].clone = in_use
    asked: list[tuple[str, int]] = []

    def pr_state(repo: str, number: int) -> str:
        """Fail for the first pull request; the second is merged."""
        asked.append((repo, number))
        if number == 1:
            raise subprocess.CalledProcessError(1, "gh", stderr="offline")
        return "MERGED"

    monkeypatch.setattr(checkouts, "pr_state", pr_state)
    state = State(pending=entries, managed_clones=[in_use, vanished, clone])
    capsys.readouterr()
    cleanup_finished(state)
    assert asked == [("octo/project", 1), ("octo/project", 2)]
    assert [entry.pr_number for entry in load_state().pending] == [1]
    assert load_state().managed_clones == [in_use]
    assert not clone.exists()
    assert [
        line.partition("] ")[2] for line in capsys.readouterr().out.splitlines()
    ] == [
        "octo/project#1: cannot check state: offline",
        "octo/project#2 is merged; cleaning up",
        f"deleting {clone}: it did not exist before its agent run",
    ]


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
        pytest.param(
            fall_behind,
            "is 1 commit(s) behind origin/main; run `make self-update` to use them",
            id="behind",
        ),
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
    spy: Callable[[Any, str], Spy],
) -> None:
    """Outside a git checkout, such as an unpacked copy, there is nothing to check."""
    exists = spy(Path, "exists")
    assert stale_checkout(tmp_path) is None
    assert exists.calls == [((tmp_path / ".git",), {})]


def test_stale_checkout_without_a_remote(tmp_path: Path) -> None:
    """A clone without a remote cannot be behind it."""
    git("init", "--quiet", "--initial-branch=main", tmp_path)
    git("-C", tmp_path, "commit", "--quiet", "--allow-empty", "-m", "initial")
    assert stale_checkout(tmp_path) is None


@pytest.mark.parametrize(
    ("arrange", "commands"),
    [
        pytest.param(switch_branch, 2, id="branch"),
        pytest.param(fall_behind, 4, id="behind"),
    ],
)
def test_stale_checkout_commands(
    clone: Path,
    spy: Callable[[Any, str], Spy],
    arrange: Callable[[Path], None],
    commands: int,
) -> None:
    """The checks read git's output whatever its exit code; the branch check stops."""
    arrange(clone)
    git("-C", clone, "remote", "set-head", "origin", "main")
    sh = spy(checkouts, "sh")
    stale_checkout(clone)
    git_in = ("git", "-C", clone)
    assert (
        sh.calls
        == [
            (
                (*git_in, "symbolic-ref", "--short", "refs/remotes/origin/HEAD"),
                {"check": False},
            ),
            ((*git_in, "branch", "--show-current"), {"check": False}),
            ((*git_in, "fetch", "--quiet", "origin", "main"), {"check": False}),
            ((*git_in, "rev-list", "--count", "HEAD..origin/main"), {"check": False}),
        ][:commands]
    )


def test_stale_checkout_follows_origins_default_branch(clone: Path) -> None:
    """The default branch is origin's, whatever its name."""
    git("-C", clone, "push", "--quiet", "origin", "HEAD:trunk")
    git("-C", clone, "fetch", "--quiet", "origin")
    git("-C", clone, "remote", "set-head", "origin", "trunk")
    assert stale_checkout(clone) == (
        f"{clone} has main checked out, not trunk, and scheduled runs use that"
        " code; run `git switch trunk`, then `make self-update`"
    )


def test_a_failed_final_lookup_preserves_agent_work_and_its_managed_clone(
    clone: Path,
    config: Config,
    commands: FakeCommands,
    make_repo: Callable[..., Repo],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An API outage preserves committed and uncommitted work through cleanup."""
    commands.install("caffeinate")
    config.label = None
    save_state(State(managed_clones=[clone]))

    def agent(_agent: object, worktree: Path, *_args: object) -> int:
        """Leave both a local commit and an uncommitted file."""
        assert load_state().recovery[0].worktree == worktree
        (worktree / "README.md").write_text("agent commit\n")
        git("-C", worktree, "commit", "--quiet", "-am", "agent work")
        (worktree / "notes.txt").write_text("unfinished work\n")
        git("-C", worktree, "switch", "--quiet", "-c", "agent/own-branch")
        return 0

    def offline(*_args: object) -> None:
        """Fail the final PR lookup as a transient GitHub outage would."""
        raise subprocess.CalledProcessError(1, "gh", stderr="offline")

    monkeypatch.setattr(runner, "run_agent", agent)
    monkeypatch.setattr(runner, "find_pr", offline)
    prompt = Prompt(name="p", path="README.md", cadence="monthly")
    repo = make_repo()
    assert runner.run_plan(config, "python", [(repo, prompt)]) == ["project p: failed"]

    saved = load_state()
    [checkout] = saved.recovery
    assert checkout.final_branch == "agent/own-branch"
    assert (checkout.worktree / "notes.txt").read_text() == "unfinished work\n"
    assert git("-C", checkout.worktree, "log", "-1", "--format=%s") == "agent work"
    assert saved.managed_clones == [clone]
    assert saved.is_due(prompt, repo, "monthly")

    # Even a user removing the worktree must not make cleanup discard the
    # clone containing the retained local branches.
    git("-C", clone, "worktree", "remove", "--force", checkout.worktree)
    cleanup_finished(saved)
    assert clone.exists()
    assert load_state().recovery == [checkout]
