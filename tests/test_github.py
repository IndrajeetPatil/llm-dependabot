"""Tests for parsing gh output and finding a run's pull request."""

import datetime as dt
import json
from typing import TYPE_CHECKING

from llm_dependabot import github
from llm_dependabot.github import GitHubRepo, PullRequest, find_pr, gh_json

if TYPE_CHECKING:
    from collections.abc import Callable

    import pytest

    from llm_dependabot.github import Repo

STARTED = dt.datetime(2026, 11, 26, 9, tzinfo=dt.UTC)


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


def fake_gh(
    monkeypatch: pytest.MonkeyPatch,
    by_head: list[PullRequest],
    recent: list[PullRequest],
) -> None:
    """Fake gh pr list, by head branch and by recent author."""

    def gh(_kind: object, *args: str) -> list[PullRequest]:
        """Answer a gh pr list call."""
        return by_head if "--head" in args else recent

    monkeypatch.setattr(github, "gh_json", gh)


def test_find_pr_prefers_the_run_branch(
    monkeypatch: pytest.MonkeyPatch, make_repo: Callable[..., Repo]
) -> None:
    """The newest pull request from the run's branch wins."""
    fake_gh(monkeypatch, [pull_request(3, STARTED), pull_request(5, STARTED)], [])
    found = find_pr(make_repo(), "chore/update-deps", STARTED)
    assert found is not None
    assert found.number == 5


def test_find_pr_falls_back_to_pull_requests_opened_since_the_start(
    monkeypatch: pytest.MonkeyPatch, make_repo: Callable[..., Repo]
) -> None:
    """Without one on the run's branch, a pull request opened since the start counts."""
    before = STARTED - dt.timedelta(minutes=1)
    recent = [pull_request(7, before), pull_request(8, STARTED)]
    fake_gh(monkeypatch, [], recent)
    found = find_pr(make_repo(), "chore/update-deps", STARTED)
    assert found is not None
    assert found.number == 8


def test_find_pr_finds_nothing(
    monkeypatch: pytest.MonkeyPatch, make_repo: Callable[..., Repo]
) -> None:
    """Pull requests from before the run do not count."""
    fake_gh(monkeypatch, [], [pull_request(7, STARTED - dt.timedelta(days=1))])
    assert find_pr(make_repo(), "chore/update-deps", STARTED) is None
