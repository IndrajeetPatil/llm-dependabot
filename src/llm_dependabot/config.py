"""The settings in config.yaml and the private repository list in private.yaml."""

import datetime as dt
import json
from pathlib import Path
from typing import Literal, cast, get_args

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveFloat,
    ValidationError,
    field_validator,
    model_validator,
)

from llm_dependabot.paths import CONFIG_FILE, NAME, PRIVATE_FILE
from llm_dependabot.shell import fail, local_today

type Weekday = Literal[
    "Sunday",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
]
WEEKDAYS: tuple[str, ...] = cast(
    "tuple[str, ...]",
    get_args(Weekday.__value__),
)  # launchd: Sunday is 0
WEEKEND = frozenset({"Saturday", "Sunday"})

type Cadence = Literal["weekly", "monthly"]

PROMPT = "{prompt}"
TIMEOUT_HOURS = "{timeout_hours}"


class Strict(BaseModel):
    """A model that rejects unknown keys and never coerces between types."""

    model_config = ConfigDict(strict=True, extra="forbid")


class Prompt(Strict):
    """A prompt that repositories opt into by committing it at `path`."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    path: str
    cadence: Cadence = "weekly"


class Group(Strict):
    """Repositories of some primary languages, run weekly at one time."""

    model_config = ConfigDict(frozen=True)

    name: str
    languages: list[str]
    weekday: Weekday
    time: dt.time
    # Per-prompt cadence overrides for this group, by prompt name.
    cadence: dict[str, Cadence] = {}

    def cadence_for(self, prompt: Prompt) -> Cadence:
        """How often the prompt runs in this group, after any override."""
        return self.cadence.get(prompt.name, prompt.cadence)


class Agent(Strict):
    """The coding agent that runs each prompt, and how to call it."""

    model_config = ConfigDict(frozen=True)

    name: str
    command: list[str] = Field(min_length=1)
    check: list[str] | None = None

    def argv(self, prompt: str, timeout_hours: float) -> tuple[list[str], bool]:
        """Return the command line, and whether the prompt goes to stdin.

        An argument that is exactly {prompt} becomes the prompt's text; without
        one, the prompt is written to the agent's standard input instead.
        """
        argv = [
            prompt
            if arg == PROMPT
            else arg.replace(TIMEOUT_HOURS, f"{timeout_hours:g}")
            for arg in self.command
        ]
        return argv, PROMPT not in self.command


class PullRequestLabel(Strict):
    """The label added to every pull request a run opens."""

    model_config = ConfigDict(frozen=True)

    name: str
    color: str = Field(pattern=r"^[0-9a-fA-F]{6}$")
    description: str = ""


class Config(Strict):
    """The validated contents of config.yaml, plus the private repositories."""

    owner: str
    # A reverse-DNS prefix you own, such as com.example; see bundle_id.
    bundle_id_prefix: str = Field(pattern=r"^[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*$")
    prompts: list[Prompt] = Field(min_length=1)
    clone_root: Path
    agent: Agent
    agent_timeout_hours: PositiveFloat
    cleanup_interval_hours: PositiveFloat
    skip_weekends: bool = True
    label: PullRequestLabel | None = None
    groups: list[Group]
    # Filled in from private.yaml, never from config.yaml.
    private_repos: frozenset[str] = Field(default=frozenset(), exclude=True)

    @property
    def bundle_id(self) -> str:
        """The app's bundle identifier, which also prefixes the launchd labels."""
        return f"{self.bundle_id_prefix}.{NAME}"

    def launchd_label(self, job: str) -> str:
        """The launchd label of a job, such as a group's run or the cleanup."""
        return f"{self.bundle_id}.{job}"

    @field_validator("clone_root")
    @classmethod
    def _expand(cls, value: Path) -> Path:
        return value.expanduser()

    @model_validator(mode="after")
    def _consistent(self) -> Config:
        for kind, names in (
            ("group", [g.name for g in self.groups]),
            ("prompt", [p.name for p in self.prompts]),
        ):
            if len(names) != len(set(names)):
                msg = f"{kind} names must be unique"
                raise ValueError(msg)
        known = {p.name for p in self.prompts}
        for group in self.groups:
            if unknown := set(group.cadence) - known:
                msg = (
                    f"group {group.name!r} sets a cadence for unknown prompts"
                    f" {sorted(unknown)}"
                )
                raise ValueError(msg)
            if self.skip_weekends and group.weekday in WEEKEND:
                msg = (
                    f"group {group.name!r} is scheduled on a {group.weekday},"
                    " but skip_weekends is on"
                )
                raise ValueError(msg)
        return self

    def prompt(self, name: str) -> Prompt:
        """The prompt with this name, or fail listing the configured ones."""
        prompt = next((p for p in self.prompts if p.name == name), None)
        if prompt is None:
            choices = [p.name for p in self.prompts]
            fail(f"unknown prompt {name!r}; choose from {choices}")
        return prompt

    def group(self, name: str) -> Group:
        """The group with this name, or fail listing the configured ones."""
        group = next((g for g in self.groups if g.name == name), None)
        if group is None:
            choices = [g.name for g in self.groups]
            fail(f"unknown group {name!r}; choose from {choices}")
        return group


class PrivateRepos(Strict):
    """The contents of private.yaml: names of private repositories to include."""

    repos: list[str] = []


def yaml_to_json(path: Path) -> str:
    """Re-encode a YAML file as JSON, for strict validation in JSON mode.

    JSON mode accepts the strings YAML holds for times and paths, while still
    rejecting values YAML parsed as another type, such as an unquoted 9:00
    (the integer 540).
    """
    return json.dumps(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


def load_config() -> Config:
    """Read config.yaml plus the private repository list from private.yaml."""
    try:
        config = Config.model_validate_json(yaml_to_json(CONFIG_FILE))
        repos = []
        if PRIVATE_FILE.exists():
            repos = PrivateRepos.model_validate_json(yaml_to_json(PRIVATE_FILE)).repos
    except ValidationError as exc:
        fail(f"invalid configuration: {exc}")
    config.private_repos = frozenset(repos)
    return config


def is_weekend(config: Config) -> bool:
    """Whether scheduled jobs should do nothing today."""
    return config.skip_weekends and f"{local_today():%A}" in WEEKEND
