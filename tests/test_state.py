"""Tests for due-state tracking and the state file."""

import datetime as dt
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from llm_dependabot import state as state_module
from llm_dependabot.state import State, load_state, save_state

if TYPE_CHECKING:
    from collections.abc import Callable

    from llm_dependabot.config import Cadence, Config
    from llm_dependabot.github import Repo
    from tests.conftest import Spy

TODAY = dt.date(2026, 11, 26)

pytestmark: pytest.MarkDecorator = pytest.mark.usefixtures("today")


@pytest.fixture
def today(monkeypatch: pytest.MonkeyPatch) -> dt.date:
    """Fix today's date."""
    monkeypatch.setattr(state_module, "local_today", lambda: TODAY)
    return TODAY


@pytest.mark.parametrize(
    ("cadence", "last", "due"),
    [
        pytest.param("weekly", TODAY, True, id="weekly, ran today"),
        pytest.param("monthly", None, True, id="monthly, never ran"),
        pytest.param(
            "monthly",
            dt.date(2026, 11, 2),
            False,
            id="monthly, ran this month",
        ),
        pytest.param(
            "monthly",
            dt.date(2026, 10, 30),
            True,
            id="monthly, ran last month",
        ),
        pytest.param(
            "monthly",
            dt.date(2025, 11, 26),
            True,
            id="monthly, same month last year",
        ),
    ],
)
def test_is_due(
    config: Config,
    make_repo: Callable[..., Repo],
    cadence: Cadence,
    last: dt.date | None,
    *,
    due: bool,
) -> None:
    """Weekly prompts are always due; monthly ones once per calendar month."""
    repo = make_repo()
    runs = {} if last is None else {f"simplify-codebase {repo.full_name}": last}
    state = State(last_runs=runs)
    assert state.is_due(config.prompt("simplify-codebase"), repo, cadence) is due


def test_record_run_saves_the_date(
    config: Config,
    make_repo: Callable[..., Repo],
) -> None:
    """Recording a run saves today's date to the state file."""
    state = State()
    state.record_run(config.prompt("simplify-codebase"), make_repo())
    assert load_state().last_runs == {"simplify-codebase octo/project": TODAY}


def test_a_missing_state_file_is_an_empty_state() -> None:
    """Without a state file, the state is empty."""
    assert load_state() == State()


def test_state_survives_a_round_trip(spy: Callable[[Any, str], Spy]) -> None:
    """Saving and loading returns the same state, atomically."""
    write_text = spy(Path, "write_text")
    state = State(managed_clones=[], last_runs={"update-deps octo/a": TODAY})
    save_state(state)
    assert load_state() == state
    [((written, _), _)] = write_text.calls
    assert written == state_module.STATE_FILE.with_suffix(".tmp")
    assert not written.exists()


def test_the_state_file_is_indented() -> None:
    """The state file is indented, so people can read it."""
    save_state(State())
    assert state_module.STATE_FILE.read_text().startswith('{\n  "pending": [],\n')


def test_existing_state_without_recovery_still_loads() -> None:
    """State files from earlier versions gain an empty recovery list."""
    state_module.STATE_FILE.parent.mkdir(parents=True)
    state_module.STATE_FILE.write_text(
        '{"pending": [], "managed_clones": [], "last_runs": {}}',
    )
    assert load_state() == State()
