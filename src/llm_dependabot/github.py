"""Repositories and pull requests, read and changed through the gh CLI."""

import datetime as dt
from typing import TYPE_CHECKING, Literal, cast

from pydantic import BaseModel, ConfigDict, TypeAdapter
from pydantic.alias_generators import to_camel

from llm_dependabot.config import Strict
from llm_dependabot.shell import sh, succeeds

if TYPE_CHECKING:
    from llm_dependabot.config import Config, PullRequestLabel

FINISHED_PR_STATES = frozenset({"MERGED", "CLOSED"})


class Repo(Strict):
    """An owned repository eligible for agent runs."""

    model_config = ConfigDict(frozen=True)

    owner: str
    name: str
    default_branch: str
    # Names of the configured prompts the repository carries.
    prompts: tuple[str, ...] = ()

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


class GitHubModel(BaseModel):
    """An object in gh's JSON output, with camelCase keys."""

    model_config = ConfigDict(strict=True, alias_generator=to_camel)


class Language(GitHubModel):
    name: str


class BranchRef(GitHubModel):
    name: str


class GitHubRepo(GitHubModel):
    name: str
    visibility: Literal["PUBLIC", "PRIVATE", "INTERNAL"]
    primary_language: Language | None
    # Empty repositories have no default branch.
    default_branch_ref: BranchRef | None

    def repo(self, owner: str) -> Repo:
        branch = cast("BranchRef", self.default_branch_ref)
        return Repo(owner=owner, name=self.name, default_branch=branch.name)


class PullRequest(GitHubModel):
    number: int
    url: str
    state: Literal["OPEN", "CLOSED", "MERGED"]
    created_at: dt.datetime


class PullRequestState(GitHubModel):
    state: Literal["OPEN", "CLOSED", "MERGED"]


def gh_json[T](kind: type[T], *args: str) -> T:
    """Run gh and validate its JSON output as `kind`."""
    return TypeAdapter(kind).validate_json(sh("gh", *args))


def owned_repos(config: Config, visibility: str | None = None) -> list[GitHubRepo]:
    args = ["--visibility", visibility] if visibility is not None else []
    listing = gh_json(
        list[GitHubRepo],
        "repo",
        "list",
        config.owner,
        "--source",
        "--no-archived",
        "--limit",
        "1000",
        *args,
        "--json",
        "name,visibility,primaryLanguage,defaultBranchRef",
    )
    return sorted(
        (item for item in listing if item.default_branch_ref),
        key=lambda item: item.name.lower(),
    )


def has_prompt(repo: Repo, prompt_path: str) -> bool:
    return succeeds(
        "gh",
        "api",
        f"repos/{repo.full_name}/contents/{prompt_path}?ref={repo.default_branch}",
        "--silent",
    )


def pr_state(repo: str, number: int) -> str:
    return gh_json(
        PullRequestState,
        "pr",
        "view",
        str(number),
        "-R",
        repo,
        "--json",
        "state",
    ).state


def find_pr(repo: Repo, branch: str, started: dt.datetime) -> PullRequest | None:
    fields = "number,url,state,createdAt"
    base = ["pr", "list", "-R", repo.full_name, "--state", "all", "--json", fields]
    prs = gh_json(list[PullRequest], *base, "--head", branch)
    if not prs:
        # The agent may have pushed to a branch of its own choosing.
        recent = gh_json(list[PullRequest], *base, "--author", "@me", "--limit", "20")
        prs = [p for p in recent if p.created_at >= started]
    return max(prs, key=lambda p: p.number, default=None)


def add_label(repo: Repo, number: int, label: PullRequestLabel) -> None:
    """Label a pull request, creating or updating the label in the repository."""
    sh(
        "gh",
        "label",
        "create",
        label.name,
        "-R",
        repo.full_name,
        "--force",
        "--color",
        label.color,
        "--description",
        label.description,
    )
    sh(
        "gh",
        "api",
        "-X",
        "POST",
        f"repos/{repo.full_name}/issues/{number}/labels",
        "-f",
        f"labels[]={label.name}",
    )
