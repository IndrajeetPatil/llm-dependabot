"""Tests for planning due prompts, running the agent, and labelling its pull request."""

import datetime as dt
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple, override

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

    import filelock

    from llm_dependabot.config import Config
    from tests.conftest import FakeCommands, Spy

TODAY: dt.date = dt.datetime.now().astimezone().date()
STARTED: dt.datetime = dt.datetime(2026, 11, 26, 9, tzinfo=dt.UTC)
LABEL: PullRequestLabel = PullRequestLabel(name="bot", color="5fbfae")


def logged(capsys: pytest.CaptureFixture[str]) -> list[str]:
    """The messages logged so far, without their timestamps."""
    return [line.partition("] ")[2] for line in capsys.readouterr().out.splitlines()]


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
            "import sys; print(sys.stdin.read()); sys.exit(3)",
            False,
            3,
            id="stdin",
        ),
    ],
)
def test_run_agent(
    tmp_path: Path,
    code: str,
    exit_code: int,
    *,
    via_argument: bool,
) -> None:
    """The prompt reaches the agent, its output is logged, and its exit code returns."""
    command = [sys.executable, "-c", code, *(["{prompt}"] if via_argument else [])]
    log = tmp_path / "run.log"
    agent = Agent(name="python", command=command)
    assert run_agent(agent, tmp_path, "the prompt", log, 1) == exit_code
    assert log.read_text() == "the prompt\n"


class RecordingPopen(subprocess.Popen[str]):
    """A real process that records what it was sent, and how long it had."""

    sent: ClassVar[list[tuple[str | None, float | None]]] = []

    @override
    def communicate(
        self,
        input: str | None = None,
        timeout: float | None = None,
    ) -> tuple[str, str]:
        """Record the input and timeout, then talk to the process."""
        self.sent.append((input, timeout))
        return super().communicate(input, timeout=timeout)


@pytest.mark.parametrize(
    ("argument", "stdin"),
    [
        pytest.param("{prompt}", subprocess.DEVNULL, id="argument"),
        pytest.param("-", subprocess.PIPE, id="stdin"),
    ],
)
def test_run_agent_options(
    monkeypatch: pytest.MonkeyPatch,
    spy: Callable[[Any, str], Spy],
    tmp_path: Path,
    argument: str,
    stdin: int,
) -> None:
    """The agent runs in its own session, logging both streams as UTF-8.

    Its deadline leaves ten minutes beyond the agent's own timeout.
    """
    monkeypatch.setattr(RecordingPopen, "sent", [])
    monkeypatch.setattr(runner.subprocess, "Popen", RecordingPopen)
    popen = spy(runner.subprocess, "Popen")
    opened = spy(Path, "open")
    log = tmp_path / "run.log"
    script = "import sys; print('out', flush=True); print('err', file=sys.stderr)"
    agent = Agent(name="python", command=[sys.executable, "-c", script, argument])
    assert run_agent(agent, tmp_path, "the prompt", log, 1.5) == 0
    assert opened.calls == [((log, "w"), {"encoding": "utf-8"})]
    [(_, options)] = popen.calls
    assert options.pop("stdout").name == str(log)
    assert options == {
        "cwd": tmp_path,
        "stdin": stdin,
        "stderr": subprocess.STDOUT,
        "start_new_session": True,
        "encoding": "utf-8",
    }
    sent = "the prompt" if stdin == subprocess.PIPE else None
    assert RecordingPopen.sent == [(sent, 1.5 * 3600 + 600)]
    assert log.read_text(encoding="utf-8") == "out\nerr\n"


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


def test_current_branch_tolerates_git_failing(
    spy: Callable[[Any, str], Spy],
    tmp_path: Path,
) -> None:
    """Outside a Git worktree, the run's own branch is assumed."""
    sh = spy(runner, "sh")
    assert current_branch(checkout_in(tmp_path)) == "chore/update-deps-1"
    assert sh.calls == [
        (("git", "-C", tmp_path, "branch", "--show-current"), {"check": False}),
    ]


@pytest.mark.parametrize("works", [True, False])
def test_label_pr(
    monkeypatch: pytest.MonkeyPatch,
    make_repo: Callable[..., Repo],
    capsys: pytest.CaptureFixture[str],
    *,
    works: bool,
) -> None:
    """Labelling reports success, and logs a gh failure instead of raising it."""
    repo = make_repo()
    added: list[tuple[Repo, int, PullRequestLabel]] = []

    def add_label(to: Repo, number: int, label: PullRequestLabel) -> None:
        """Fail like gh does, unless labelling works."""
        added.append((to, number, label))
        if not works:
            raise subprocess.CalledProcessError(1, "gh", stderr="no permission")

    monkeypatch.setattr(runner, "add_label", add_label)
    assert label_pr(repo, pull_request(7), LABEL, "project p") is works
    assert added == [(repo, 7, LABEL)]
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
        self,
        _repo: Repo,
        _branch: str,
        _started: dt.datetime,
    ) -> PullRequest | None:
        """Return or raise the next scripted result."""
        result = self.lookups[min(self.calls, len(self.lookups) - 1)]
        self.calls += 1
        if isinstance(result, Exception):
            raise result
        return result

    def label_pr(
        self,
        _repo: Repo,
        pr: PullRequest,
        _label: PullRequestLabel,
        _name: str,
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
    capsys: pytest.CaptureFixture[str],
    case: RunCase,
) -> None:
    """A run records its pull request and labels it unless the watcher did."""
    checkout = checkout_in(tmp_path)
    removed: list[Checkout] = []
    labels: list[int] = []
    repo = Repo(owner="octo", name="project", default_branch="main", prompts=("p",))
    prompt = Prompt(name="p", path="prompt.md")
    state = State()

    def record_label(
        to: Repo,
        pr: PullRequest,
        label: PullRequestLabel,
        name: str,
    ) -> bool:
        """Record which pull request was labelled after the run."""
        assert (to, label, name) == (repo, LABEL, "project p")
        labels.append(pr.number)
        return True

    def prepare_checkout(*args: object) -> Checkout:
        """The checkout, prepared for this run."""
        assert args == (repo, prompt, config, state, tmp_path / "project-p.log")
        return checkout

    def agent_pass(*args: object) -> tuple[int, PullRequest | None, set[int]]:
        """The scripted outcome of the agent's run."""
        assert args == (checkout, repo, prompt, config, "project p")
        return 0, case.pr, case.labelled_early

    monkeypatch.setattr(runner, "prepare_checkout", prepare_checkout)
    monkeypatch.setattr(runner, "agent_pass", agent_pass)
    monkeypatch.setattr(runner, "remove_checkout", removed.append)
    monkeypatch.setattr(runner, "label_pr", record_label)
    config.label = case.pr_label

    assert process_repo(repo, prompt, config, state, tmp_path) == case.summary
    assert labels == case.labelled_after
    assert logged(capsys) == (
        [f"project p: open pull request {case.pr.url}"]
        if case.pr
        else ["project p: no pull request was opened; removing the worktree"]
    )
    pending = [entry.pr_number for entry in load_state().pending]
    assert pending == ([case.pr.number] if case.pr else [])
    assert removed == ([] if case.pr else [checkout])


@pytest.mark.parametrize(
    "ignore_term",
    [
        pytest.param(False, id="cooperative"),
        pytest.param(True, id="ignores sigterm"),
    ],
)
def test_run_agent_stops_an_agent_that_outlasts_its_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    ignore_term: bool,
) -> None:
    """A timed-out agent is stopped even when it ignores graceful termination."""

    class QuickTimeout(subprocess.Popen[str]):
        """Time out after a fraction of a second instead of hours.

        Records the waits after the timeout, bounding the final one so a
        process left running fails the test instead of hanging it.
        """

        waits: ClassVar[list[float | None]] = []

        def __init__(self, args: list[str], **options: Any) -> None:
            """Start the process, which must lead its own process group."""
            assert options["start_new_session"] is True
            super().__init__(args, **options)

        @override
        def wait(self, timeout: float | None = None) -> int:
            """Record the timeout, then wait at most a few seconds."""
            if self.timed_out:
                self.waits.append(timeout)
            return super().wait(5 if timeout is None else timeout)

        timed_out = False

        @override
        def communicate(
            self,
            input: str | None = None,
            timeout: float | None = None,
        ) -> tuple[str, str]:
            """Wait briefly, whatever timeout the caller asked for."""
            del timeout
            deadline = time.monotonic() + 5
            while not (tmp_path / "ready").exists():
                if time.monotonic() > deadline:
                    self.kill()
                    pytest.fail("agent did not initialise")
                time.sleep(0.01)
            try:
                return super().communicate(input, timeout=0.1)
            finally:
                self.timed_out = True

    monkeypatch.setattr(runner.subprocess, "Popen", QuickTimeout)
    monkeypatch.setattr(QuickTimeout, "waits", [])
    monkeypatch.setattr(runner, "TERMINATE_GRACE_SECONDS", 0.1)
    handler = "signal.SIG_IGN" if ignore_term else "signal.SIG_DFL"
    agent = Agent(
        name="sleepy",
        command=[
            sys.executable,
            "-c",
            (
                "import signal,time; from pathlib import Path; "
                f"signal.signal(signal.SIGTERM, {handler}); "
                "Path('ready').touch(); time.sleep(30)"
            ),
        ],
    )
    started = time.monotonic()
    assert run_agent(agent, tmp_path, "prompt", tmp_path / "run.log", 1) == -1
    assert time.monotonic() - started < 10
    # A grace period for the leader, then a wait for the killed group.
    assert QuickTimeout.waits == [0.1, None]


def test_agent_pass_runs_the_committed_prompt(
    config: Config,
    monkeypatch: pytest.MonkeyPatch,
    spy: Callable[[Any, str], Spy],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The agent gets the prompt file's text, then the run's pull request is found."""
    (tmp_path / "prompt.md").write_text("Update everything.")
    checkout = checkout_in(tmp_path)
    found: list[tuple[Repo, str, dt.datetime]] = []

    def find_pr(repo: Repo, branch: str, started: dt.datetime) -> PullRequest:
        """Record the lookup, and find pull request 5."""
        found.append((repo, branch, started))
        return pull_request(5)

    monkeypatch.setattr(runner, "find_pr", find_pr)
    monkeypatch.setattr(runner, "current_branch", lambda _checkout: "agent/branch")
    watched = spy(runner, "labelling_early")
    config.label = LABEL
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
    assert found == [(repo, "agent/branch", STARTED)]
    assert watched.calls == [((checkout, repo, LABEL, "project p"), {})]
    assert logged(capsys) == [
        f"project p: running agent in {tmp_path} (log: {tmp_path / 'run.log'})",
        "project p: agent exited with code 0",
    ]


def test_process_repo_retains_the_checkout_when_the_agent_cannot_run(
    config: Config,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An error retains a tracked checkout for recovery, then propagates."""
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
    assert removed == []
    assert load_state().recovery == [checkout]
    assert logged(capsys) == [
        f"project p: retaining {tmp_path} for recovery (see `status`)",
    ]


@pytest.mark.parametrize(
    ("pr", "message"),
    [
        pytest.param(
            None,
            "agent exited with code 3; retained {worktree} for recovery",
            id="no pull request",
        ),
        pytest.param(
            pull_request(4),
            "agent exited with code 3; tracking"
            " https://github.com/octo/project/pull/4 for cleanup",
            id="pull request",
        ),
    ],
)
def test_process_repo_reports_a_failed_agent(
    config: Config,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    pr: PullRequest | None,
    message: str,
) -> None:
    """A failed agent's run fails, saying what happened to its work."""
    monkeypatch.setattr(runner, "prepare_checkout", lambda *_: checkout_in(tmp_path))
    monkeypatch.setattr(runner, "agent_pass", lambda *_: (3, pr, set()))
    monkeypatch.setattr(runner, "label_pr", lambda *_: True)
    repo = Repo(owner="octo", name="project", default_branch="main", prompts=("p",))
    with pytest.raises(RuntimeError) as error:
        process_repo(repo, Prompt(name="p", path="p.md"), config, State(), tmp_path)
    assert str(error.value) == message.format(worktree=tmp_path)


def test_run_plan_keeps_going_after_a_repository_fails(
    commands: FakeCommands,
    config: Config,
    monkeypatch: pytest.MonkeyPatch,
    spy: Callable[[Any, str], Spy],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every planned run is attempted, only successes count as run, then cleanup.

    The run's log folder may exist already, from an earlier run that minute.
    """
    commands.install("caffeinate")
    outcomes: dict[str, Exception | str] = {
        "ok": "ok update-deps: PR #1",
        "skip": SkipRepoError("not a git clone"),
        "boom": subprocess.CalledProcessError(1, "git", stderr="fetch failed"),
        "quiet": subprocess.CalledProcessError(1, "git", stderr=""),
        "bug": KeyError("x"),
    }
    monkeypatch.setattr(
        runner,
        "dt",
        SimpleNamespace(datetime=SimpleNamespace(now=lambda: STARTED)),
    )
    run_dir = runner.LOG_DIR / "2026-11-26-0900-python"
    run_dir.mkdir(parents=True)
    popen = spy(runner.subprocess, "Popen")

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
    plan = [
        (Repo(owner="octo", name=name, default_branch="main"), prompt)
        for name in outcomes
    ]

    assert run_plan(config, "python", plan) == [
        "ok update-deps: PR #1",
        "skip update-deps: skipped",
        "boom update-deps: failed",
        "quiet update-deps: failed",
        "bug update-deps: failed",
    ]
    assert list(load_state().last_runs) == ["update-deps octo/ok"]
    assert len(cleaned) == 1
    assert popen.calls == [((["caffeinate", "-i", "-w", str(os.getpid())],), {})]
    assert list(runner.LOG_DIR.iterdir()) == [run_dir]
    assert logged(capsys) == [
        "skip update-deps: skipped: not a git clone",
        "boom update-deps: failed: fetch failed",
        "quiet update-deps: failed: Command 'git' returned non-zero exit status 1.",
        "bug update-deps: failed: 'x'",
    ]


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
    lock = runner.filelock.FileLock

    def file_lock(path: Path, **options: Any) -> filelock.FileLock:
        """The run lock, which cleanup must not wait for."""
        assert options == {"timeout": 0}
        return lock(path, **options)

    monkeypatch.setattr(runner.filelock, "FileLock", file_lock)
    runner.cleanup()
    assert cleaned == ([State()] if cleans else [])
    assert logged(capsys) == (
        [] if cleans else ["a run is in progress; skipping cleanup"]
    )


@pytest.mark.parametrize(
    "exit_code",
    [
        pytest.param(0, id="success"),
        pytest.param(3, id="failure"),
        pytest.param(-1, id="timeout"),
    ],
)
@pytest.mark.parametrize(
    "has_pr",
    [
        pytest.param(False, id="no pr"),
        pytest.param(True, id="pr opened"),
    ],
)
def test_only_successful_agents_complete_the_monthly_cadence(
    config: Config,
    commands: FakeCommands,
    monkeypatch: pytest.MonkeyPatch,
    exit_code: int,
    *,
    has_pr: bool,
) -> None:
    """Failures stay due; PRs remain tracked, and failures without PRs are retained."""
    commands.install("caffeinate")
    config.label = None
    checkout = checkout_in(config.clone_root)
    pr = pull_request(4) if has_pr else None
    removed: list[Checkout] = []
    monkeypatch.setattr(runner, "prepare_checkout", lambda *_args: checkout)

    def agent_pass(*_args: object) -> tuple[int, PullRequest | None, set[int]]:
        """Model the agent switching to a branch of its own."""
        checkout.final_branch = "agent/own-branch"
        return exit_code, pr, set()

    monkeypatch.setattr(runner, "agent_pass", agent_pass)
    monkeypatch.setattr(runner, "remove_checkout", removed.append)
    monkeypatch.setattr(runner, "cleanup_finished", lambda _state: None)
    repo = Repo(owner="octo", name="project", default_branch="main")
    prompt = config.prompt("simplify-codebase")

    [summary] = run_plan(config, "python", [(repo, prompt)])

    saved = load_state()
    assert saved.is_due(prompt, repo, "monthly") is (exit_code != 0)
    assert ("failed" in summary) is (exit_code != 0)
    assert [entry.pr_number for entry in saved.pending] == ([4] if has_pr else [])
    retained = exit_code != 0 and not has_pr
    assert saved.recovery == ([checkout] if retained else [])
    assert removed == ([checkout] if exit_code == 0 and not has_pr else [])


def test_timeout_tolerates_an_agent_exiting_before_the_signal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A process that exits at the deadline does not turn a timeout into an error."""

    def gone(_pid: int, _signal: int) -> None:
        """Simulate the process group disappearing before each signal."""
        raise ProcessLookupError

    class Expired(subprocess.Popen[str]):
        """Report a deadline after reaping a short-lived real process."""

        @override
        def communicate(
            self,
            input: str | None = None,
            timeout: float | None = None,
        ) -> tuple[str, str]:
            """Let the process exit, then simulate the timeout race."""
            super().communicate(input, timeout=timeout)
            raise subprocess.TimeoutExpired(self.args, 0)

    monkeypatch.setattr(runner.subprocess, "Popen", Expired)
    monkeypatch.setattr(runner.os, "killpg", gone)
    agent = Agent(name="quick", command=[sys.executable, "-c", "pass"])
    assert run_agent(agent, tmp_path, "prompt", tmp_path / "run.log", 1) == -1
