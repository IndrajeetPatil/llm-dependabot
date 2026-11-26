"""Tests for parsing gh output and finding a run's pull request."""

import datetime as dt
import json
from itertools import starmap
from typing import TYPE_CHECKING, Any

import pytest

from llm_dependabot import github
from llm_dependabot.config import PullRequestLabel
from llm_dependabot.github import (
    GitHubRepo,
    PullRequest,
    add_label,
    find_pr,
    gh_json,
    has_prompt,
    owned_repos,
    pr_state,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from llm_dependabot.config import Config
    from llm_dependabot.github import Repo
    from tests.conftest import FakeCommands

STARTED: dt.datetime = dt.datetime(2026, 11, 26, 9, tzinfo=dt.UTC)


def test_gh_json_validates_camel_case_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """The camelCase JSON of gh validates into the snake_case models."""
    output = [
        {
            "name": "app",
            "visibility": "PUBLIC",
            "primaryLanguage": {"name": "Python"},
            "defaultBranchRef": {"name": "trunk"},
        },
    ]
    calls: list[tuple[str, ...]] = []

    def sh(*args: str) -> str:
        """Record the command and return the canned output."""
        calls.append(args)
        return json.dumps(output)

    monkeypatch.setattr(github, "sh", sh)
    [item] = gh_json(list[GitHubRepo], "repo", "list")
    assert calls == [("gh", "repo", "list")]
    assert item.primary_language is not None
    assert item.primary_language.name == "Python"
    assert item.repo("octo").default_branch == "trunk"


def pull_request(number: int, created: dt.datetime) -> PullRequest:
    """A pull request of octo/project, as gh reports it."""
    return PullRequest.model_validate({
        "number": number,
        "url": f"https://github.com/octo/project/pull/{number}",
        "state": "OPEN",
        "createdAt": created,
    })


BEFORE: dt.datetime = STARTED - dt.timedelta(minutes=1)


@pytest.mark.parametrize(
    ("by_head", "recent", "expected"),
    [
        pytest.param(
            [(3, STARTED), (5, STARTED)],
            [],
            5,
            id="newest on the run branch",
        ),
        pytest.param(
            [],
            [(7, BEFORE), (8, STARTED)],
            8,
            id="opened since the run started",
        ),
        pytest.param([], [(7, BEFORE)], None, id="only older pull requests"),
        pytest.param([], [], None, id="none at all"),
    ],
)
def test_find_pr(
    monkeypatch: pytest.MonkeyPatch,
    make_repo: Callable[..., Repo],
    by_head: list[tuple[int, dt.datetime]],
    recent: list[tuple[int, dt.datetime]],
    expected: int | None,
) -> None:
    """The run branch's newest pull request, else one opened since the run started."""
    answers = {
        True: list(starmap(pull_request, by_head)),
        False: list(starmap(pull_request, recent)),
    }

    def gh(_kind: object, *args: str) -> list[PullRequest]:
        """Answer gh pr list, by head branch or by recent author."""
        return answers["--head" in args]

    monkeypatch.setattr(github, "gh_json", gh)
    found = find_pr(make_repo(), "chore/update-deps", STARTED)
    assert (found.number if found else None) == expected


def listing_entry(name: str, *, default_branch: str | None = "main") -> dict[str, Any]:
    """One repository as gh repo list --json reports it."""
    branch = None if default_branch is None else {"name": default_branch}
    return {
        "name": name,
        "visibility": "PUBLIC",
        "primaryLanguage": None,
        "defaultBranchRef": branch,
    }


@pytest.mark.parametrize(
    ("visibility", "flags"),
    [
        pytest.param(None, [], id="every visibility"),
        pytest.param("private", ["--visibility", "private"], id="private only"),
    ],
)
def test_owned_repos(
    commands: FakeCommands,
    config: Config,
    visibility: str | None,
    flags: list[str],
) -> None:
    """Owned repositories come back sorted by name, leaving out empty ones."""
    listing = [
        listing_entry("beta"),
        listing_entry("Alpha"),
        listing_entry("empty", default_branch=None),
    ]
    commands.on("gh", "repo list", stdout=json.dumps(listing))
    assert [repo.name for repo in owned_repos(config, visibility)] == ["Alpha", "beta"]
    [call] = commands.calls("gh")
    assert call[:3] == ["repo", "list", "octo"]
    assert call[7:-2] == flags


@pytest.mark.parametrize(("code", "expected"), [(0, True), (1, False)])
def test_has_prompt(
    commands: FakeCommands,
    make_repo: Callable[..., Repo],
    code: int,
    *,
    expected: bool,
) -> None:
    """A prompt counts only if gh finds it on the default branch."""
    commands.on("gh", code=code)
    assert has_prompt(make_repo(), ".github/prompts/update-deps.md") is expected
    assert commands.calls("gh") == [
        [
            "api",
            "repos/octo/project/contents/.github/prompts/update-deps.md?ref=main",
            "--silent",
        ],
    ]


def test_pr_state(commands: FakeCommands) -> None:
    """A pull request's state comes from gh pr view."""
    commands.on("gh", stdout='{"state": "MERGED"}')
    assert pr_state("octo/project", 12) == "MERGED"
    assert commands.calls("gh") == [
        ["pr", "view", "12", "-R", "octo/project", "--json", "state"],
    ]


def test_add_label_creates_the_label_then_applies_it(
    commands: FakeCommands,
    make_repo: Callable[..., Repo],
) -> None:
    """The label is created or updated in the repository, then added to the PR."""
    commands.install("gh")
    label = PullRequestLabel(name="bot", color="5fbfae", description="Opened by bot")
    add_label(make_repo(), 12, label)
    assert commands.calls("gh") == [
        [
            "label",
            "create",
            "bot",
            "-R",
            "octo/project",
            "--force",
            "--color",
            "5fbfae",
            "--description",
            "Opened by bot",
        ],
        [
            "api",
            "-X",
            "POST",
            "repos/octo/project/issues/12/labels",
            "-f",
            "labels[]=bot",
        ],
    ]
