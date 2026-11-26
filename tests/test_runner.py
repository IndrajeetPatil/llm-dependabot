"""Tests for planning due prompts, running the agent, and labelling its pull request."""

import datetime as dt
import subprocess
import sys
import threading
from typing import TYPE_CHECKING, NamedTuple

import pytest
import typer

from llm_dependabot import runner
from llm_dependabot.config import Agent, Prompt, PullRequestLabel
from llm_dependabot.github import PullRequest, Repo
from llm_dependabot.runner import (
    current_branch,
    label_pr,
    labelling_early,
    planned_runs,
    process_repo,
    run_agent,
)
from llm_dependabot.state import Checkout, State, load_state

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from llm_dependabot.config import Config

TODAY: dt.date = dt.datetime.now().astimezone().date()
STARTED: dt.datetime = dt.datetime(2026, 11, 26, 9, tzinfo=dt.UTC)
LABEL: PullRequestLabel = PullRequestLabel(name="bot", color="5fbfae")


@pytest.fixture
def repos(make_repo: Callable[..., Repo]) -> list[Repo]:
    """Two repositories: one with both prompts, one with update-deps."""
    return [
        make_repo("both", "update-deps", "simplify-codebase"),
        make_repo("deps", "update-deps"),
    ]


class PlanCase(NamedTuple):
    """A planning scenario: what already ran today, what is forced, what runs."""

    group: str
    ran_today: list[str]
    forced: list[str]
    expected: list[str]


EVERYTHING: list[str] = [
    "both update-deps",
    "both simplify-codebase",
    "deps update-deps",
]


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(PlanCase("python", [], [], EVERYTHING), id="first run"),
        pytest.param(
            PlanCase(
                "python",
                ["simplify-codebase octo/both"],
                [],
                ["both update-deps", "deps update-deps"],
            ),
            id="monthly prompt ran this month",
        ),
        pytest.param(
            PlanCase("python", ["update-deps octo/deps"], [], EVERYTHING),
            id="weekly prompt ran today",
        ),
        pytest.param(
            PlanCase(
                "rest",
                ["update-deps octo/deps"],
                [],
                ["both update-deps", "both simplify-codebase"],
            ),
            id="group override makes a weekly prompt monthly",
        ),
        pytest.param(
            PlanCase(
                "python",
                ["simplify-codebase octo/both"],
                ["simplify-codebase"],
                ["both simplify-codebase"],
            ),
            id="forced prompt runs whatever its cadence",
        ),
    ],
)
def test_planned_runs(config: Config, repos: list[Repo], case: PlanCase) -> None:
    """Each repository runs the prompts it carries that are due, or forced."""
    state = State(last_runs=dict.fromkeys(case.ran_today, TODAY))
    plan = planned_runs(config, config.group(case.group), repos, state, case.forced)
    assert [f"{repo.name} {prompt.name}" for repo, prompt in plan] == case.expected


def test_an_unknown_forced_prompt_fails(config: Config, repos: list[Repo]) -> None:
    """Forcing an unknown prompt fails."""
    with pytest.raises(typer.Exit):
        planned_runs(config, config.group("python"), repos, State(), ["missing"])


@pytest.mark.parametrize(
    ("code", "via_argument", "exit_code"),
    [
        pytest.param("import sys; print(sys.argv[1])", True, 0, id="argument"),
        pytest.param(
            "import sys; print(sys.stdin.read()); sys.exit(3)", False, 3, id="stdin"
        ),
    ],
)
def test_run_agent(
    tmp_path: Path, code: str, exit_code: int, *, via_argument: bool
) -> None:
    """The prompt reaches the agent, its output is logged, and its exit code returns."""
    command = [sys.executable, "-c", code, *(["{prompt}"] if via_argument else [])]
    log = tmp_path / "run.log"
    agent = Agent(name="python", command=command)
    assert run_agent(agent, tmp_path, "the prompt", log, 1) == exit_code
    assert log.read_text() == "the prompt\n"


def pull_request(number: int) -> PullRequest:
    """An open pull request of octo/project, as gh reports it."""
    return PullRequest.model_validate({
        "number": number,
        "url": f"https://github.com/octo/project/pull/{number}",
        "state": "OPEN",
        "createdAt": STARTED,
    })


def checkout_in(worktree: Path) -> Checkout:
    """A checkout of octo/project whose worktree is the given directory."""
    return Checkout(
        repo="octo/project",
        clone=worktree,
        worktree=worktree,
        branch="chore/update-deps-1",
        log=worktree / "run.log",
        started=STARTED,
    )


@pytest.mark.parametrize(
    ("switch_to", "expected"),
    [
        pytest.param("agent/own-branch", "agent/own-branch", id="agent's branch"),
        pytest.param(None, "chore/update-deps-1", id="detached head"),
    ],
)
def test_current_branch(tmp_path: Path, switch_to: str | None, expected: str) -> None:
    """The worktree's branch, or the run's own one when no branch is checked out."""
    git = ["git", "-C", str(tmp_path), "-c", "user.name=T", "-c", "user.email=t@t"]
    subprocess.run([*git, "init", "--quiet"], check=True)
    subprocess.run([*git, "commit", "--quiet", "--allow-empty", "-m", "c"], check=True)
    target = ["--detach"] if switch_to is None else ["-b", switch_to]
    subprocess.run([*git, "checkout", "--quiet", *target], check=True)
    assert current_branch(checkout_in(tmp_path)) == expected


@pytest.mark.parametrize("works", [True, False])
def test_label_pr(
    monkeypatch: pytest.MonkeyPatch,
    make_repo: Callable[..., Repo],
    capsys: pytest.CaptureFixture[str],
    *,
    works: bool,
) -> None:
    """Labelling reports success, and logs a gh failure instead of raising it."""

    def add_label(_repo: Repo, _number: int, _label: PullRequestLabel) -> None:
        """Fail like gh does, unless labelling works."""
        if not works:
            raise subprocess.CalledProcessError(1, "gh", stderr="no permission")

    monkeypatch.setattr(runner, "add_label", add_label)
    assert label_pr(make_repo(), pull_request(7), LABEL, "project p") is works
    assert ("no permission" in capsys.readouterr().out) is not works


class FakeGitHub:
    """Pull request lookups and labels, answered from a script of results."""

    def __init__(self, lookups: list[PullRequest | Exception | None]) -> None:
        """Answer each lookup with the next result, then the last one forever."""
        self.lookups: list[PullRequest | Exception | None] = lookups
        self.calls: int = 0
        self.labelled: list[int] = []
        self.done: threading.Event = threading.Event()

    def find_pr(
        self, _repo: Repo, _branch: str, _started: dt.datetime
    ) -> PullRequest | None:
        """Return or raise the next scripted result."""
        result = self.lookups[min(self.calls, len(self.lookups) - 1)]
        self.calls += 1
        if isinstance(result, Exception):
            raise result
        return result

    def label_pr(
        self, _repo: Repo, pr: PullRequest, _label: PullRequestLabel, _name: str
    ) -> bool:
        """Record the label and signal that the watcher has done its work."""
        self.labelled.append(pr.number)
        self.done.set()
        return True


@pytest.fixture
def github(monkeypatch: pytest.MonkeyPatch) -> Callable[..., FakeGitHub]:
    """Install a fake GitHub for the watcher, polling every few milliseconds."""

    def install(*lookups: PullRequest | Exception | None) -> FakeGitHub:
        """Fake the lookups in order."""
        fake = FakeGitHub(list(lookups))
        monkeypatch.setattr(runner, "LABEL_POLL_SECONDS", 0.005)
        monkeypatch.setattr(runner, "find_pr", fake.find_pr)
        monkeypatch.setattr(runner, "label_pr", fake.label_pr)
        monkeypatch.setattr(runner, "current_branch", lambda checkout: checkout.branch)
        return fake

    return install


def test_the_watcher_labels_the_pull_request_once_it_exists(
    github: Callable[..., FakeGitHub],
    make_repo: Callable[..., Repo],
    tmp_path: Path,
) -> None:
    """The watcher retries through misses and errors, labels once, then stops."""
    fake = github(None, RuntimeError("gh is down"), pull_request(9))
    with labelling_early(checkout_in(tmp_path), make_repo(), LABEL, "p") as labelled:
        assert fake.done.wait(5)
    assert labelled == {9}
    assert fake.labelled == [9]
    assert fake.calls == 3


@pytest.mark.parametrize(
    ("pr_label", "polls"),
    [
        pytest.param(None, False, id="no label: never starts"),
        pytest.param(LABEL, True, id="label: stops at exit"),
    ],
)
def test_the_watcher_stops_when_the_agent_exits(
    github: Callable[..., FakeGitHub],
    make_repo: Callable[..., Repo],
    tmp_path: Path,
    pr_label: PullRequestLabel | None,
    *,
    polls: bool,
) -> None:
    """Leaving the block stops and joins the watcher, which labelled nothing."""
    fake = github(None)
    with labelling_early(checkout_in(tmp_path), make_repo(), pr_label, "p") as labelled:
        assert fake.done.wait(0.05) is False
    assert labelled == set()
    assert fake.labelled == []
    assert (fake.calls > 0) is polls


class RunCase(NamedTuple):
    """An agent run's outcome, and what process_repo should do about it."""

    pr: PullRequest | None
    labelled_early: set[int]
    pr_label: PullRequestLabel | None
    labelled_after: list[int]
    summary: str


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(
            RunCase(pull_request(4), set(), LABEL, [4], "project p: PR #4"),
            id="labelled after the run",
        ),
        pytest.param(
            RunCase(pull_request(4), {4}, LABEL, [], "project p: PR #4"),
            id="already labelled while the agent ran",
        ),
        pytest.param(
            RunCase(pull_request(4), set(), None, [], "project p: PR #4"),
            id="no label configured",
        ),
        pytest.param(
            RunCase(None, set(), LABEL, [], "project p: no PR (exit 0)"),
            id="no pull request",
        ),
    ],
)
def test_process_repo(
    config: Config,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    case: RunCase,
) -> None:
    """A run records its pull request and labels it unless the watcher did."""
    checkout = checkout_in(tmp_path)
    removed: list[Checkout] = []
    labels: list[int] = []

    def record_label(
        _repo: Repo, pr: PullRequest, _label: PullRequestLabel, _name: str
    ) -> bool:
        """Record which pull request was labelled after the run."""
        labels.append(pr.number)
        return True

    monkeypatch.setattr(runner, "prepare_checkout", lambda *_args: checkout)
    monkeypatch.setattr(
        runner, "agent_pass", lambda *_args: (0, case.pr, case.labelled_early)
    )
    monkeypatch.setattr(runner, "remove_checkout", removed.append)
    monkeypatch.setattr(runner, "label_pr", record_label)
    config.label = case.pr_label

    repo = Repo(owner="octo", name="project", default_branch="main", prompts=("p",))
    prompt = Prompt(name="p", path="prompt.md")
    assert process_repo(repo, prompt, config, State(), tmp_path) == case.summary
    assert labels == case.labelled_after
    pending = [entry.pr_number for entry in load_state().pending]
    assert pending == ([case.pr.number] if case.pr else [])
    assert removed == ([] if case.pr else [checkout])
