"""Tests for due-state tracking and the state file."""

import datetime as dt
from typing import TYPE_CHECKING

import pytest

from llm_dependabot import state as state_module
from llm_dependabot.state import State, load_state, save_state

if TYPE_CHECKING:
    from collections.abc import Callable

    from llm_dependabot.config import Config
    from llm_dependabot.github import Repo

TODAY = dt.date(2026, 11, 26)

pytestmark: pytest.MarkDecorator = pytest.mark.usefixtures("today")


@pytest.fixture
def today(monkeypatch: pytest.MonkeyPatch) -> dt.date:
    """Fix today's date."""
    monkeypatch.setattr(state_module, "local_today", lambda: TODAY)
    return TODAY


def test_a_weekly_prompt_is_always_due(
    config: Config, make_repo: Callable[..., Repo]
) -> None:
    """A weekly prompt is due even if it ran today."""
    state = State(last_runs={f"update-deps {make_repo().full_name}": TODAY})
    assert state.is_due(config.prompt("update-deps"), make_repo(), "weekly")


@pytest.mark.parametrize(
    ("last", "due"),
    [
        (None, True),
        (dt.date(2026, 11, 2), False),
        (dt.date(2026, 10, 30), True),
        (dt.date(2025, 11, 26), True),  # the same month a year earlier
    ],
)
def test_a_monthly_prompt_is_due_once_a_calendar_month(
    config: Config,
    make_repo: Callable[..., Repo],
    last: dt.date | None,
    *,
    due: bool,
) -> None:
    """A monthly prompt is due once per calendar month."""
    repo = make_repo()
    runs = {} if last is None else {f"simplify-codebase {repo.full_name}": last}
    state = State(last_runs=runs)
    assert state.is_due(config.prompt("simplify-codebase"), repo, "monthly") is due


def test_record_run_saves_the_date(
    config: Config, make_repo: Callable[..., Repo]
) -> None:
    """Recording a run saves today's date to the state file."""
    state = State()
    state.record_run(config.prompt("simplify-codebase"), make_repo())
    assert load_state().last_runs == {"simplify-codebase octo/project": TODAY}


def test_a_missing_state_file_is_an_empty_state() -> None:
    """Without a state file, the state is empty."""
    assert load_state() == State()


def test_state_survives_a_round_trip() -> None:
    """Saving and loading returns the same state, atomically."""
    state = State(managed_clones=[], last_runs={"update-deps octo/a": TODAY})
    save_state(state)
    assert load_state() == state
    assert not state_module.STATE_FILE.with_suffix(".tmp").exists()
