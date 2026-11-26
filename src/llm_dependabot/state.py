"""What runs left behind: pull requests, recovery checkouts, clones, and dates."""

import datetime as dt
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import Field

from llm_dependabot.config import Strict
from llm_dependabot.paths import STATE_DIR, STATE_FILE
from llm_dependabot.shell import local_today

if TYPE_CHECKING:
    from llm_dependabot.config import Cadence, Prompt
    from llm_dependabot.github import Repo


class Checkout(Strict):
    """A worktree on a fresh branch, created for one agent run."""

    repo: str
    clone: Path
    worktree: Path
    branch: str
    final_branch: str | None = None
    log: Path
    started: dt.datetime


class Pending(Checkout):
    """A checkout whose pull request is still open."""

    pr_number: int
    pr_url: str


class State(Strict):
    """Everything runs leave behind, kept in state.json."""

    pending: list[Pending] = Field(default_factory=list)
    # Interrupted or failed runs whose work needs manual recovery.
    recovery: list[Checkout] = Field(default_factory=list)
    managed_clones: list[Path] = Field(default_factory=list)
    # When each prompt last ran in each repository, keyed "prompt owner/repo".
    last_runs: dict[str, dt.date] = Field(default_factory=dict)

    def is_due(self, prompt: Prompt, repo: Repo, cadence: Cadence) -> bool:
        """Whether a scheduled run should run the prompt in the repository.

        Weekly prompts run at every scheduled run. Monthly ones run at the
        first scheduled run of each calendar month, or the next one if that
        was missed or failed.
        """
        if cadence == "weekly":
            return True
        last = self.last_runs.get(f"{prompt.name} {repo.full_name}")
        today = local_today()
        return last is None or (last.year, last.month) != (today.year, today.month)

    def record_run(self, prompt: Prompt, repo: Repo) -> None:
        """Record that the prompt ran in the repository today."""
        self.last_runs[f"{prompt.name} {repo.full_name}"] = local_today()
        save_state(self)


def load_state() -> State:
    """The saved state, or an empty one before the first run."""
    if STATE_FILE.exists():
        return State.model_validate_json(STATE_FILE.read_text())
    return State()


def save_state(state: State) -> None:
    """Write the state atomically."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(state.model_dump_json(indent=2) + "\n")
    tmp.replace(STATE_FILE)
