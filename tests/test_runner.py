"""Tests for planning due prompts and running the agent."""

import datetime as dt
import sys
from typing import TYPE_CHECKING

import pytest
import typer

from llm_dependabot.config import Agent
from llm_dependabot.runner import planned_runs, run_agent
from llm_dependabot.state import State

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from llm_dependabot.config import Config, Prompt
    from llm_dependabot.github import Repo


@pytest.fixture
def repos(make_repo: Callable[..., Repo]) -> list[Repo]:
    """Two repositories: one with both prompts, one with update-deps."""
    return [
        make_repo("both", "update-deps", "simplify-codebase"),
        make_repo("deps", "update-deps"),
    ]


def names(plan: list[tuple[Repo, Prompt]]) -> list[str]:
    """The plan as 'repo prompt' strings."""
    return [f"{repo.name} {prompt.name}" for repo, prompt in plan]


def test_every_due_prompt_runs(config: Config, repos: list[Repo]) -> None:
    """Every prompt a repository carries is due on its first run."""
    plan = planned_runs(config, config.group("python"), repos, State(), [])
    assert names(plan) == [
        "both update-deps",
        "both simplify-codebase",
        "deps update-deps",
    ]


def test_a_prompt_that_ran_this_month_is_not_due(
    config: Config, repos: list[Repo]
) -> None:
    """A monthly prompt that ran this month is left out."""
    today = dt.datetime.now().astimezone().date()
    state = State(last_runs={"simplify-codebase octo/both": today})
    plan = planned_runs(config, config.group("python"), repos, state, [])
    assert names(plan) == ["both update-deps", "deps update-deps"]


def test_a_group_cadence_override_applies(config: Config, repos: list[Repo]) -> None:
    """A group's monthly override holds back a weekly prompt."""
    today = dt.datetime.now().astimezone().date()
    state = State(last_runs={"update-deps octo/deps": today})
    plan = planned_runs(config, config.group("rest"), repos, state, [])
    assert "deps update-deps" not in names(plan)


def test_a_forced_prompt_runs_whatever_its_cadence(
    config: Config, repos: list[Repo]
) -> None:
    """A forced prompt runs, and only it runs."""
    today = dt.datetime.now().astimezone().date()
    state = State(last_runs={"simplify-codebase octo/both": today})
    forced = ["simplify-codebase"]
    plan = planned_runs(config, config.group("python"), repos, state, forced)
    assert names(plan) == ["both simplify-codebase"]


def test_an_unknown_forced_prompt_fails(config: Config, repos: list[Repo]) -> None:
    """Forcing an unknown prompt fails."""
    with pytest.raises(typer.Exit):
        planned_runs(config, config.group("python"), repos, State(), ["missing"])


def python_agent(code: str, *, via_argument: bool) -> Agent:
    """An agent that runs Python code, with or without a prompt argument."""
    command = [sys.executable, "-c", code]
    return Agent(
        name="python", command=[*command, "{prompt}"] if via_argument else command
    )


def test_run_agent_passes_the_prompt_as_an_argument(tmp_path: Path) -> None:
    """The prompt reaches the agent as an argument."""
    log = tmp_path / "run.log"
    agent = python_agent("import sys; print(sys.argv[1])", via_argument=True)
    assert run_agent(agent, tmp_path, "the prompt", log, 1) == 0
    assert log.read_text() == "the prompt\n"


def test_run_agent_writes_the_prompt_to_stdin(tmp_path: Path) -> None:
    """The prompt reaches the agent on stdin, and its exit code returns."""
    log = tmp_path / "run.log"
    agent = python_agent(
        "import sys; print(sys.stdin.read()); sys.exit(3)", via_argument=False
    )
    assert run_agent(agent, tmp_path, "from stdin", log, 1) == 3
    assert log.read_text() == "from stdin\n"
