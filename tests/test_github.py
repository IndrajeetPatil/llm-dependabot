"""Tests for parsing gh output and finding a run's pull request."""

import datetime as dt
import json
from itertools import starmap
from typing import TYPE_CHECKING

import pytest

from llm_dependabot import github
from llm_dependabot.github import GitHubRepo, PullRequest, find_pr, gh_json

if TYPE_CHECKING:
    from collections.abc import Callable

    from llm_dependabot.github import Repo

STARTED: dt.datetime = dt.datetime(2026, 11, 26, 9, tzinfo=dt.UTC)


def test_gh_json_validates_camel_case_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """The camelCase JSON of gh validates into the snake_case models."""
    output = [
        {
            "name": "app",
            "visibility": "PUBLIC",
            "primaryLanguage": {"name": "Python"},
            "defaultBranchRef": {"name": "trunk"},
        }
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
            [(3, STARTED), (5, STARTED)], [], 5, id="newest on the run branch"
        ),
        pytest.param(
            [], [(7, BEFORE), (8, STARTED)], 8, id="opened since the run started"
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
