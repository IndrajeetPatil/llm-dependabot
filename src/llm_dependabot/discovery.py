"""Find the owned repositories that carry prompts, and sort them into groups."""

from typing import TYPE_CHECKING

from llm_dependabot.github import has_prompt, owned_repos
from llm_dependabot.paths import PRIVATE_FILE
from llm_dependabot.shell import log

if TYPE_CHECKING:
    from llm_dependabot.config import Config
    from llm_dependabot.github import Repo

CATCH_ALL = "*"


def group_for(language: str, config: Config) -> str | None:
    """The group a primary language belongs to, if any."""
    for group in config.groups:
        if language in group.languages:
            return group.name
    for group in config.groups:
        if CATCH_ALL in group.languages:
            return group.name
    return None


def prompts_in(repo: Repo, config: Config) -> tuple[str, ...]:
    """Names of the configured prompts committed to the repository."""
    return tuple(p.name for p in config.prompts if has_prompt(repo, p.path))


def discover(config: Config, group: str | None = None) -> dict[str, list[Repo]]:
    """Map group name to the repositories in it that carry at least one prompt.

    Public repositories are included automatically; private ones only when
    private.yaml lists them.
    """
    listing = owned_repos(config)
    private = config.private_repos
    owned_private = {i.name for i in listing if i.visibility != "PUBLIC"}
    if missing := private - owned_private:
        log(f"{PRIVATE_FILE.name}: not owned private repositories: {sorted(missing)}")
    grouped: dict[str, list[Repo]] = {g.name: [] for g in config.groups}
    for item in listing:
        if item.visibility != "PUBLIC" and item.name not in private:
            continue
        language = item.primary_language.name if item.primary_language else ""
        name = group_for(language, config)
        if name is None or (group is not None and name != group):
            continue
        repo = item.repo(config.owner)
        if prompts := prompts_in(repo, config):
            grouped[name].append(repo.model_copy(update={"prompts": prompts}))
    return grouped
