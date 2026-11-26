"""Tests for planning due prompts, running the agent, and labelling its pull request."""

import datetime as dt
import os
import subprocess
import sys
import threading
from typing import TYPE_CHECKING, NamedTuple, override

import pytest
import typer

from llm_dependabot import runner
from llm_dependabot.checkouts import SkipRepoError
from llm_dependabot.config import Agent, Prompt, PullRequestLabel
from llm_dependabot.github import PullRequest, Repo
from llm_dependabot.runner import (
    current_branch,
    label_pr,
    labelling_early,
    planned_runs,
    process_repo,
    run_agent,
    run_plan,
)
from llm_dependabot.state import Checkout, State, load_state

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from llm_dependabot.config import Config
    from tests.conftest import FakeCommands

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


def test_run_agent_stops_an_agent_that_outlasts_its_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A hung agent's whole process group is stopped, and the run reports -1."""

    class QuickTimeout(subprocess.Popen[str]):
        """Time out after a fraction of a second instead of hours."""

        @override
        def communicate(
            self,
            input: str | None = None,
            timeout: float | None = None,
        ) -> tuple[str, str]:
            """Wait briefly, whatever timeout the caller asked for."""
            del timeout
            return super().communicate(input, timeout=0.2)

    monkeypatch.setattr(runner.subprocess, "Popen", QuickTimeout)
    agent = Agent(
        name="sleepy", command=[sys.executable, "-c", "import time; time.sleep(30)"]
    )
    assert run_agent(agent, tmp_path, "prompt", tmp_path / "run.log", 1) == -1


def test_agent_pass_runs_the_committed_prompt(
    config: Config, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The agent gets the prompt file's text, then the run's pull request is found."""
    (tmp_path / "prompt.md").write_text("Update everything.")
    checkout = checkout_in(tmp_path)
    found: list[str] = []

    def find_pr(_repo: Repo, branch: str, _started: dt.datetime) -> PullRequest:
        """Record the branch looked up, and find pull request 5."""
        found.append(branch)
        return pull_request(5)

    monkeypatch.setattr(runner, "find_pr", find_pr)
    monkeypatch.setattr(runner, "current_branch", lambda _checkout: "agent/branch")
    config.label = None
    config.agent = Agent(
        name="echo",
        command=[sys.executable, "-c", "import sys; print(sys.argv[1])", "{prompt}"],
    )
    repo = Repo(owner="octo", name="project", default_branch="main")
    prompt = Prompt(name="p", path="prompt.md")
    code, pr, labelled = runner.agent_pass(checkout, repo, prompt, config, "project p")
    assert (code, pr, labelled) == (0, pull_request(5), set())
    assert checkout.log.read_text() == "Update everything.\n"
    assert checkout.final_branch == "agent/branch"
    assert found == ["agent/branch"]


def test_process_repo_removes_the_checkout_when_the_agent_cannot_run(
    config: Config, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An error during the agent pass removes the worktree, then propagates."""
    checkout = checkout_in(tmp_path)
    removed: list[Checkout] = []

    def agent_pass(*_args: object) -> tuple[int, PullRequest | None, set[int]]:
        """Fail as a missing prompt file would."""
        raise FileNotFoundError("prompt.md")

    monkeypatch.setattr(runner, "prepare_checkout", lambda *_args: checkout)
    monkeypatch.setattr(runner, "agent_pass", agent_pass)
    monkeypatch.setattr(runner, "remove_checkout", removed.append)
    repo = Repo(owner="octo", name="project", default_branch="main", prompts=("p",))
    with pytest.raises(FileNotFoundError):
        process_repo(repo, Prompt(name="p", path="p.md"), config, State(), tmp_path)
    assert removed == [checkout]


def test_run_plan_keeps_going_after_a_repository_fails(
    commands: FakeCommands,
    config: Config,
    monkeypatch: pytest.MonkeyPatch,
    make_repo: Callable[..., Repo],
) -> None:
    """Every planned run is attempted, only successes count as run, then cleanup."""
    commands.install("caffeinate")
    outcomes: dict[str, Exception | str] = {
        "ok": "ok update-deps: PR #1",
        "skip": SkipRepoError("not a git clone"),
        "boom": subprocess.CalledProcessError(1, "git", stderr="fetch failed"),
    }

    def process_repo(repo: Repo, *_args: object) -> str:
        """Succeed, skip, or fail, by repository name."""
        outcome = outcomes[repo.name]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    cleaned: list[State] = []
    monkeypatch.setattr(runner, "process_repo", process_repo)
    monkeypatch.setattr(runner, "cleanup_finished", cleaned.append)
    prompt = config.prompt("update-deps")
    plan = [(make_repo(name, "update-deps"), prompt) for name in outcomes]

    assert run_plan(config, "python", plan) == [
        "ok update-deps: PR #1",
        "skip update-deps: skipped",
        "boom update-deps: failed",
    ]
    assert list(load_state().last_runs) == ["update-deps octo/ok"]
    assert len(cleaned) == 1
    assert commands.calls("caffeinate") in ([], [["-i", "-w", str(os.getpid())]])
    [run_dir] = runner.LOG_DIR.iterdir()
    assert run_dir.name.endswith("-python")


@pytest.fixture
def lock_held() -> Iterator[None]:
    """Hold the run lock from another process, as a running group would."""
    runner.LOCK_FILE.parent.mkdir(parents=True)
    code = (
        "import fcntl, sys, time; f = open(sys.argv[1], 'w');"
        " fcntl.flock(f, fcntl.LOCK_EX); print('held', flush=True); time.sleep(30)"
    )
    with subprocess.Popen(
        [sys.executable, "-c", code, str(runner.LOCK_FILE)],
        stdout=subprocess.PIPE,
        text=True,
    ) as holder:
        assert holder.stdout is not None
        assert holder.stdout.readline() == "held\n"
        yield
        holder.kill()


@pytest.mark.parametrize(
    ("fixtures", "cleans"),
    [
        pytest.param([], True, id="no run"),
        pytest.param(["lock_held"], False, id="a run holds the lock"),
    ],
)
def test_cleanup_waits_for_no_run(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    request: pytest.FixtureRequest,
    fixtures: list[str],
    *,
    cleans: bool,
) -> None:
    """Cleanup runs unless a run holds the lock, in which case it skips."""
    for fixture in fixtures:
        request.getfixturevalue(fixture)
    cleaned: list[State] = []
    monkeypatch.setattr(runner, "cleanup_finished", cleaned.append)
    runner.cleanup()
    assert len(cleaned) == (1 if cleans else 0)
    assert ("a run is in progress" in capsys.readouterr().out) is not cleans
