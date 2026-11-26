from typing import TYPE_CHECKING

import pytest

from llm_dependabot import discovery
from llm_dependabot.discovery import discover, group_for
from llm_dependabot.github import GitHubRepo

if TYPE_CHECKING:
    from llm_dependabot.config import Config
    from llm_dependabot.github import Repo


@pytest.mark.parametrize(
    ("language", "group"),
    [("Python", "python"), ("Rust", "rest"), ("", "rest")],
)
def test_group_for_falls_back_to_the_catch_all(
    config: Config, language: str, group: str
) -> None:
    assert group_for(language, config) == group


def test_group_for_without_a_catch_all(config: Config) -> None:
    config.groups.pop()
    assert group_for("Rust", config) is None


def listing(*items: tuple[str, str, str | None]) -> list[GitHubRepo]:
    return [
        GitHubRepo.model_validate({
            "name": name,
            "visibility": visibility,
            "primaryLanguage": {"name": language} if language is not None else None,
            "defaultBranchRef": {"name": "main"},
        })
        for name, visibility, language in items
    ]


@pytest.fixture
def github(monkeypatch: pytest.MonkeyPatch) -> dict[str, set[str]]:
    """Fake gh: the listing below, and the prompts each repository carries."""
    prompts = {
        "app": {".github/prompts/update-deps.md"},
        "lib": {
            ".github/prompts/update-deps.md",
            ".github/prompts/simplify-codebase.md",
        },
        "secret": {".github/prompts/update-deps.md"},
        "hidden": {".github/prompts/update-deps.md"},
        "tool": {".github/prompts/update-deps.md"},
    }
    repos = listing(
        ("app", "PUBLIC", "Python"),
        ("bare", "PUBLIC", "Python"),
        ("lib", "PUBLIC", "Python"),
        ("secret", "PRIVATE", "Python"),
        ("hidden", "PRIVATE", "Python"),
        ("tool", "PUBLIC", "Go"),
    )
    monkeypatch.setattr(discovery, "owned_repos", lambda _config: repos)

    def has_prompt(repo: Repo, path: str) -> bool:
        return path in prompts.get(repo.name, set())

    monkeypatch.setattr(discovery, "has_prompt", has_prompt)
    return prompts


@pytest.mark.usefixtures("github")
def test_discover_groups_repositories_that_carry_prompts(config: Config) -> None:
    config.private_repos = frozenset({"secret", "gone"})
    grouped = discover(config)
    assert {name: [r.name for r in repos] for name, repos in grouped.items()} == {
        "python": ["app", "lib", "secret"],
        "rest": ["tool"],
    }
    lib = grouped["python"][1]
    assert lib.prompts == ("update-deps", "simplify-codebase")
    assert lib.full_name == "octo/lib"


@pytest.mark.usefixtures("github")
def test_discover_one_group(config: Config) -> None:
    assert discover(config, "rest") == {
        "python": [],
        "rest": [discover(config)["rest"][0]],
    }
