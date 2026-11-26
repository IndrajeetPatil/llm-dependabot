#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.15"
# dependencies = [
#   "filelock>=4.3.1",
#   "pydantic>=2.14.4",
#   "pyyaml>=6.0.4",
#   "typer>=0.29.2",
# ]
# ///
"""Run each repository's prompts with a coding agent on a weekly or monthly cadence."""

import datetime as dt
import json
import os
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Annotated, Any, Literal, NoReturn, cast, get_args
lazy import hashlib
lazy import html
lazy import plistlib
lazy import shlex
lazy import tempfile

import typer
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveFloat,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic.alias_generators import to_camel
lazy import filelock
lazy import yaml

SCRIPT = Path(__file__).resolve()
ROOT = SCRIPT.parent
CONFIG_FILE = ROOT / "config.yaml"
PRIVATE_FILE = ROOT / "private.yaml"
APP_SOURCE = ROOT / "app"

NAME = "llm-dependabot"
APP_NAME = "LLM Dependabot"
BUNDLE_ID = f"com.indrajeetpatil.{NAME}"
LAUNCH_AGENTS = Path.home() / "Library/LaunchAgents"
LOG_DIR = Path.home() / "Library/Logs" / NAME
STATE_DIR = Path.home() / "Library/Application Support" / NAME
STATE_FILE = STATE_DIR / "state.json"
# Serialises runs and cleanups across processes; filelock creates STATE_DIR.
LOCK_FILE = STATE_DIR / "lock"
WORKTREE_ROOT = Path.home() / "Library/Caches" / NAME / "worktrees"
APP_BUNDLE = STATE_DIR / f"{APP_NAME}.app"
LAUNCHER = APP_BUNDLE / "Contents/MacOS" / NAME
FULL_DISK_ACCESS_PANE = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"
)
CATCH_ALL = "*"
FINISHED_PR_STATES = frozenset({"MERGED", "CLOSED"})
BREWFILE = ROOT / "Brewfile"

type Weekday = Literal[
    "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"
]
WEEKDAYS: tuple[str, ...] = cast(
    "tuple[str, ...]", get_args(Weekday.__value__)
)  # launchd: Sunday is 0
WEEKEND = frozenset({"Saturday", "Sunday"})

type Cadence = Literal["weekly", "monthly"]

app = typer.Typer(
    help=__doc__,
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
)


# --------------------------------------------------------------------------- #
# Configuration and state
# --------------------------------------------------------------------------- #


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
    model_config = ConfigDict(frozen=True)

    name: str
    languages: list[str]
    weekday: Weekday
    time: dt.time
    # Per-prompt cadence overrides for this group, by prompt name.
    cadence: dict[str, Cadence] = {}

    @property
    def label(self) -> str:
        return f"{BUNDLE_ID}.{self.name}"


PROMPT = "{prompt}"
TIMEOUT_HOURS = "{timeout_hours}"


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


class Config(Strict):
    owner: str
    prompts: list[Prompt] = Field(min_length=1)
    clone_root: Path
    agent: Agent
    agent_timeout_hours: PositiveFloat
    cleanup_interval_hours: PositiveFloat
    skip_weekends: bool = True
    groups: list[Group]
    # Filled in from private.yaml, never from config.yaml.
    private_repos: frozenset[str] = Field(default=frozenset(), exclude=True)

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

    def cadence(self, group: Group, prompt: Prompt) -> Cadence:
        return group.cadence.get(prompt.name, prompt.cadence)

    def prompt(self, name: str) -> Prompt:
        prompt = next((p for p in self.prompts if p.name == name), None)
        if prompt is None:
            choices = [p.name for p in self.prompts]
            fail(f"unknown prompt {name!r}; choose from {choices}")
        return prompt

    def group(self, name: str) -> Group:
        group = next((g for g in self.groups if g.name == name), None)
        if group is None:
            choices = [g.name for g in self.groups]
            fail(f"unknown group {name!r}; choose from {choices}")
        return group


class PrivateRepos(Strict):
    repos: list[str] = []


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
    pending: list[Pending] = []
    managed_clones: list[Path] = []
    # When each prompt last ran in each repository, keyed "prompt owner/repo".
    last_runs: dict[str, dt.date] = {}

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
        self.last_runs[f"{prompt.name} {repo.full_name}"] = local_today()
        save_state(self)


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


class SkipRepoError(Exception):
    """A repository cannot be processed this run."""


def local_today() -> dt.date:
    return dt.datetime.now().astimezone().date()


def fail(message: str) -> NoReturn:
    typer.secho(message, err=True, fg="red")
    raise typer.Exit(1)


def yaml_to_json(path: Path) -> str:
    """Re-encode a YAML file as JSON, for strict validation in JSON mode.

    JSON mode accepts the strings YAML holds for times and paths, while still
    rejecting values YAML parsed as another type, such as an unquoted 9:00
    (the integer 540).
    """
    return json.dumps(yaml.safe_load(path.read_text()) or {})


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


def load_state() -> State:
    if STATE_FILE.exists():
        return State.model_validate_json(STATE_FILE.read_text())
    return State()


def save_state(state: State) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(state.model_dump_json(indent=2) + "\n")
    tmp.replace(STATE_FILE)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def log(message: str) -> None:
    print(f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] {message}", flush=True)


def sh(*args: str | Path, cwd: Path | None = None, check: bool = True) -> str:
    result = subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        check=check,
    )
    return result.stdout.strip()


def succeeds(*args: str | Path, timeout: float = 120) -> bool:
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError, subprocess.TimeoutExpired:
        return False
    return result.returncode == 0


def interactive(*args: str) -> int:
    """Run a command attached to the terminal, so it can prompt the user."""
    return subprocess.run(args, check=False).returncode


def gh_json[T](kind: type[T], *args: str) -> T:
    """Run gh and validate its JSON output as `kind`."""
    return TypeAdapter(kind).validate_json(sh("gh", *args))


def notify(title: str, message: str) -> None:
    script = (
        f"display notification {json.dumps(message)} with title {json.dumps(title)}"
    )
    subprocess.run(["osascript", "-e", script], check=False, capture_output=True)


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #


def group_for(language: str, config: Config) -> str | None:
    for group in config.groups:
        if language in group.languages:
            return group.name
    for group in config.groups:
        if CATCH_ALL in group.languages:
            return group.name
    return None


def has_prompt(repo: Repo, prompt_path: str) -> bool:
    return succeeds(
        "gh",
        "api",
        f"repos/{repo.full_name}/contents/{prompt_path}?ref={repo.default_branch}",
        "--silent",
    )


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


# --------------------------------------------------------------------------- #
# Checkouts
# --------------------------------------------------------------------------- #


def remote_matches(clone: Path, repo: Repo) -> bool:
    url = sh("git", "-C", clone, "remote", "get-url", "origin", check=False)
    return url.lower().removesuffix(".git").endswith(repo.full_name.lower())


def prepare_checkout(
    repo: Repo, prompt: Prompt, config: Config, state: State, log_path: Path
) -> Checkout:
    """Create a worktree on a fresh branch off the default branch.

    The agent works in a separate worktree so an existing clone's checked-out
    branch and uncommitted work are never touched.
    """
    clone = config.clone_root / repo.name
    if (clone / ".git").exists():
        if not remote_matches(clone, repo):
            msg = f"{clone} is a clone of a different repository"
            raise SkipRepoError(msg)
    elif clone.exists():
        msg = f"{clone} exists but is not a git clone"
        raise SkipRepoError(msg)
    else:
        log(f"{repo.name}: no local copy, cloning into {clone}")
        sh("gh", "repo", "clone", repo.full_name, clone, "--", "--quiet")
        state.managed_clones.append(clone)
        save_state(state)

    sh("git", "-C", clone, "fetch", "--prune", "--quiet", "origin")
    started = dt.datetime.now(dt.UTC).replace(microsecond=0)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    checkout = Checkout(
        repo=repo.full_name,
        clone=clone,
        worktree=WORKTREE_ROOT / f"{repo.name}-{prompt.name}-{stamp}",
        branch=f"chore/{prompt.name}-{stamp}",
        log=log_path,
        started=started,
    )
    WORKTREE_ROOT.mkdir(parents=True, exist_ok=True)
    sh(
        "git",
        "-C",
        clone,
        "worktree",
        "add",
        "--quiet",
        "--no-track",
        "-b",
        checkout.branch,
        checkout.worktree,
        f"origin/{repo.default_branch}",
    )
    return checkout


def remove_checkout(checkout: Checkout) -> None:
    clone = checkout.clone
    if not clone.exists():
        return
    if checkout.worktree.exists():
        sh("git", "-C", clone, "worktree", "remove", "--force", checkout.worktree,
           check=False)  # fmt: skip
    sh("git", "-C", clone, "worktree", "prune", check=False)
    for branch in {checkout.branch, checkout.final_branch or checkout.branch}:
        sh("git", "-C", clone, "branch", "-D", branch, check=False)


def clone_is_disposable(clone: Path) -> tuple[bool, str]:
    if sh("git", "-C", clone, "status", "--porcelain", check=False):
        return False, "has uncommitted changes"
    worktrees = sh("git", "-C", clone, "worktree", "list", "--porcelain", check=False)
    if worktrees.count("worktree ") > 1:
        return False, "has other worktrees"
    if sh("git", "-C", clone, "log", "--branches", "--not", "--remotes", "--oneline",
          check=False):  # fmt: skip
        return False, "has local commits that are not on the remote"
    return True, ""


def delete_unused_managed_clones(state: State) -> None:
    """Delete clones this tool created once no pending pull request needs them."""
    in_use = {entry.clone for entry in state.pending}
    kept = []
    for clone in state.managed_clones:
        if clone in in_use:
            kept.append(clone)
            continue
        if not clone.exists():
            continue
        disposable, reason = clone_is_disposable(clone)
        if disposable:
            log(f"deleting {clone}: it did not exist before its agent run")
            shutil.rmtree(clone)
        else:
            log(f"keeping {clone} for now: it {reason}")
            kept.append(clone)
    state.managed_clones = kept
    save_state(state)


def cleanup_finished(state: State) -> None:
    remaining = []
    for entry in state.pending:
        pr_ref = f"{entry.repo}#{entry.pr_number}"
        try:
            pr_state = gh_json(
                PullRequestState,
                "pr",
                "view",
                str(entry.pr_number),
                "-R",
                entry.repo,
                "--json",
                "state",
            ).state
        except subprocess.CalledProcessError as exc:
            log(f"{pr_ref}: cannot check state: {exc.stderr}")
            remaining.append(entry)
            continue
        if pr_state in FINISHED_PR_STATES:
            log(f"{pr_ref} is {pr_state.lower()}; cleaning up")
            remove_checkout(entry)
        else:
            remaining.append(entry)
    state.pending = remaining
    save_state(state)
    delete_unused_managed_clones(state)


# --------------------------------------------------------------------------- #
# Agent run
# --------------------------------------------------------------------------- #


def run_agent(
    agent: Agent, worktree: Path, prompt: str, log_path: Path, timeout_hours: float
) -> int:
    argv, via_stdin = agent.argv(prompt, timeout_hours)
    with log_path.open("w") as out:
        proc = subprocess.Popen(
            argv,
            cwd=worktree,
            stdin=subprocess.PIPE if via_stdin else subprocess.DEVNULL,
            stdout=out,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            text=True,
        )
        try:
            # Agents with a timeout of their own stop first; this stops the rest.
            proc.communicate(
                prompt if via_stdin else None, timeout=timeout_hours * 3600 + 600
            )
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait()
            return -1
        return proc.wait()


def find_pr(repo: Repo, branch: str, started: dt.datetime) -> PullRequest | None:
    fields = "number,url,state,createdAt"
    base = ["pr", "list", "-R", repo.full_name, "--state", "all", "--json", fields]
    prs = gh_json(list[PullRequest], *base, "--head", branch)
    if not prs:
        # The agent may have pushed to a branch of its own choosing.
        recent = gh_json(list[PullRequest], *base, "--author", "@me", "--limit", "20")
        prs = [p for p in recent if p.created_at >= started]
    return max(prs, key=lambda p: p.number, default=None)


def process_repo(
    repo: Repo, prompt: Prompt, config: Config, state: State, run_dir: Path
) -> str:
    """Run one prompt in one repository; return a one-line summary."""
    label = f"{repo.name} {prompt.name}"
    log_path = run_dir / f"{repo.name}-{prompt.name}.log"
    checkout = prepare_checkout(repo, prompt, config, state, log_path)
    try:
        # The prompt is passed verbatim, exactly as committed in the repository.
        text = (checkout.worktree / prompt.path).read_text()
        log(f"{label}: running agent in {checkout.worktree} (log: {checkout.log})")
        code = run_agent(
            config.agent,
            checkout.worktree,
            text,
            checkout.log,
            config.agent_timeout_hours,
        )
        log(f"{label}: agent exited with code {code}")
        current = sh(
            "git", "-C", checkout.worktree, "branch", "--show-current", check=False
        )
        checkout.final_branch = current or checkout.branch
        pr = find_pr(repo, checkout.final_branch, checkout.started)
    except Exception:
        remove_checkout(checkout)
        raise

    if pr is None:
        log(f"{label}: no pull request was opened; removing the worktree")
        remove_checkout(checkout)
        return f"{label}: no PR (exit {code})"

    log(f"{label}: {pr.state.lower()} pull request {pr.url}")
    state.pending.append(
        Pending(**checkout.model_dump(), pr_number=pr.number, pr_url=pr.url)
    )
    save_state(state)
    return f"{label}: PR #{pr.number}"


# --------------------------------------------------------------------------- #
# launchd and the LLM Dependabot app
# --------------------------------------------------------------------------- #


def launchctl(*args: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["launchctl", *args], capture_output=True, text=True, check=False
    )


def gui_domain() -> str:
    return f"gui/{os.getuid()}"


def plist_for(
    label: str, shell_command: str, schedule: dict[str, Any], log_name: str
) -> dict[str, Any]:
    return {
        "Label": label,
        # Shows the jobs as "LLM Dependabot" in System Settings > General >
        # Login Items rather than as a bare shell.
        "AssociatedBundleIdentifiers": [BUNDLE_ID],
        # The app's launcher holds the Full Disk Access grant (see
        # app/launcher.c). A login, interactive zsh picks up the same PATH
        # (Homebrew, uv, pnpm, the agent, gh) and keychain-backed credentials as a
        # terminal session.
        "ProgramArguments": [
            str(LAUNCHER),
            "/bin/zsh",
            "-l",
            "-i",
            "-c",
            shell_command,
        ],
        "StandardOutPath": str(LOG_DIR / log_name),
        "StandardErrorPath": str(LOG_DIR / log_name),
        **schedule,
    }


def desired_agents(config: Config) -> dict[str, dict[str, Any]]:
    script = shlex.quote(str(SCRIPT))
    agents = {}
    for group in config.groups:
        when = {
            "Weekday": WEEKDAYS.index(group.weekday),
            "Hour": group.time.hour,
            "Minute": group.time.minute,
        }
        agents[group.label] = plist_for(
            group.label,
            f"exec {script} run {shlex.quote(group.name)} --scheduled",
            {"StartCalendarInterval": when},
            f"{group.name}.log",
        )
    label = f"{BUNDLE_ID}.cleanup"
    agents[label] = plist_for(
        label,
        f"exec {script} cleanup --scheduled",
        {"StartInterval": int(config.cleanup_interval_hours * 3600), "RunAtLoad": True},
        "cleanup.log",
    )
    return agents


def unload(label: str) -> None:
    launchctl("bootout", f"{gui_domain()}/{label}")
    (LAUNCH_AGENTS / f"{label}.plist").unlink(missing_ok=True)


def installed_labels() -> list[str]:
    return sorted(p.stem for p in LAUNCH_AGENTS.glob(f"{BUNDLE_ID}.*.plist"))


def running_jobs() -> list[str]:
    """Labels of installed agents whose job is running right now."""
    return [
        label
        for label in installed_labels()
        if re.search(
            r"^\tstate = running$",
            launchctl("print", f"{gui_domain()}/{label}").stdout,
            re.MULTILINE,
        )
    ]


def app_info() -> dict[str, Any]:
    return {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleExecutable": NAME,
        "CFBundleIconFile": "AppIcon",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "1.0",
        "LSUIElement": True,  # no Dock icon
    }


def build_icon(source: Path, icns: Path) -> None:
    with tempfile.TemporaryDirectory(suffix=".iconset") as iconset:
        for size in (16, 32, 128, 256, 512):
            for scale, suffix in ((1, ""), (2, "@2x")):
                out = Path(iconset) / f"icon_{size}x{size}{suffix}.png"
                pixels = str(size * scale)
                sh("sips", "-z", pixels, pixels, source, "--out", out)
        sh("iconutil", "-c", "icns", iconset, "-o", icns)


def build_app() -> bool:
    """Build the LLM Dependabot app; return True if it changed.

    macOS ties the Full Disk Access grant to the app's code signature, so the
    app is rebuilt, and needs granting again, only when its sources change.
    """
    sources = [APP_SOURCE / "launcher.c", APP_SOURCE / "icon.png"]
    digest = hashlib.sha256()
    for path in sources:
        digest.update(path.read_bytes())
    digest.update(json.dumps(app_info(), sort_keys=True).encode())
    stamp = STATE_DIR / "app.sha256"
    if LAUNCHER.exists() and stamp.exists() and stamp.read_text() == digest.hexdigest():
        return False

    shutil.rmtree(APP_BUNDLE, ignore_errors=True)
    contents = APP_BUNDLE / "Contents"
    (contents / "Resources").mkdir(parents=True)
    LAUNCHER.parent.mkdir()
    (contents / "Info.plist").write_bytes(plistlib.dumps(app_info()))
    sh("clang", "-O2", "-Wall", "-Werror", "-o", LAUNCHER, sources[0])
    build_icon(sources[1], contents / "Resources/AppIcon.icns")
    sh("codesign", "--force", "--sign", "-", "--identifier", BUNDLE_ID, APP_BUNDLE)
    stamp.write_text(digest.hexdigest())
    return True


def full_disk_access_granted(path: Path) -> bool:
    """Check that a launchd job started through the app can read path.

    This runs a throwaway agent, so it exercises the same privacy checks as
    the scheduled jobs rather than those of the current terminal. A job
    without access may instead hang on a privacy prompt; it is stopped after
    ten seconds and counts as not granted.
    """
    label = f"{BUNDLE_ID}.access-check"
    plist_path = STATE_DIR / f"{label}.plist"
    plist_path.write_bytes(
        plistlib.dumps({
            "Label": label,
            "ProgramArguments": [str(LAUNCHER), "/bin/ls", str(path)],
            "RunAtLoad": True,
            "StandardOutPath": "/dev/null",
            "StandardErrorPath": "/dev/null",
        })
    )
    target = f"{gui_domain()}/{label}"
    launchctl("bootout", target)
    launchctl("bootstrap", gui_domain(), plist_path)
    code = None
    for _ in range(100):
        if match := re.search(
            r"last exit code = (\d+)", launchctl("print", target).stdout
        ):
            code = int(match[1])
            break
        time.sleep(0.1)
    launchctl("bootout", target)
    plist_path.unlink(missing_ok=True)
    return code == 0


def show_full_disk_access_steps() -> None:
    typer.echo(
        "\nmacOS blocks launchd jobs from ~/Documents and similar folders unless"
        f" their program has Full Disk Access. Drag {APP_NAME} from the Finder"
        " window into System Settings > Privacy & Security > Full Disk Access"
        " (or click + and choose it), then switch it on:\n"
        f"  {APP_BUNDLE}\n"
        f"If macOS instead asks whether {APP_NAME} may access a folder, the"
        " check timed out waiting for it; dismiss the prompt and use the"
        " setting above.\n"
    )
    typer.launch(FULL_DISK_ACCESS_PANE)
    typer.launch(str(APP_BUNDLE), locate=True)


def install_agents(config: Config) -> None:
    """Build the app, then write and load the launchd agents."""
    if busy := running_jobs():
        fail(
            f"{', '.join(busy)} is running; reinstalling would stop it."
            " Try again once it finishes (see `status`)."
        )
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if build_app():
        log(f"built {APP_BUNDLE}")
    for label in installed_labels():
        unload(label)
    LAUNCH_AGENTS.mkdir(parents=True, exist_ok=True)
    for label, plist in desired_agents(config).items():
        path = LAUNCH_AGENTS / f"{label}.plist"
        path.write_bytes(plistlib.dumps(plist))
        result = launchctl("bootstrap", gui_domain(), path)
        if result.returncode != 0:
            fail(f"launchctl bootstrap {label} failed: {result.stderr.strip()}")
        log(f"loaded {label}")


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #


def is_weekend(config: Config) -> bool:
    return config.skip_weekends and f"{local_today():%A}" in WEEKEND


def planned_runs(
    config: Config, group: Group, repos: list[Repo], state: State, forced: list[str]
) -> list[tuple[Repo, Prompt]]:
    """The (repository, prompt) pairs to run, in order.

    Prompts named with --prompt always run; otherwise each prompt runs when
    its cadence makes it due.
    """
    prompts = [config.prompt(name) for name in forced] or config.prompts
    return [
        (repo, prompt)
        for repo in repos
        for prompt in prompts
        if prompt.name in repo.prompts
        and (forced or state.is_due(prompt, repo, config.cadence(group, prompt)))
    ]


@app.command()
def run(
    group: str,
    repo: Annotated[
        list[str] | None, typer.Option(help="Limit to this repository.")
    ] = None,
    prompt: Annotated[
        list[str] | None,
        typer.Option(help="Run this prompt whatever its cadence."),
    ] = None,
    *,
    dry_run: Annotated[bool, typer.Option(help="Only list what would run.")] = False,
    scheduled: Annotated[
        bool, typer.Option(hidden=True, help="Started by launchd.")
    ] = False,
) -> None:
    """Run the prompts that are due in every repository in GROUP."""
    config = load_config()
    if scheduled and is_weekend(config):
        log(f"group {group}: skipped, since it is the weekend")
        return
    chosen = config.group(group)
    repos = discover(config, group)[group]
    if repo is not None:
        repos = [r for r in repos if r.name in repo]
    plan = planned_runs(config, chosen, repos, load_state(), prompt or [])
    summary = ", ".join(f"{r.name} {p.name}" for r, p in plan)
    log(f"group {group}: {summary or 'nothing due'}")
    if dry_run or not plan:
        return

    with filelock.FileLock(LOCK_FILE):
        # Keep the Mac awake (idle sleep) for as long as this process runs.
        caffeinate = subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])
        run_dir = LOG_DIR / f"{dt.datetime.now():%Y-%m-%d-%H%M}-{group}"
        run_dir.mkdir(parents=True, exist_ok=True)
        state = load_state()
        results = []
        for item, task in plan:
            label = f"{item.name} {task.name}"
            try:
                results.append(process_repo(item, task, config, state, run_dir))
                state.record_run(task, item)
            except SkipRepoError as exc:
                log(f"{label}: skipped: {exc}")
                results.append(f"{label}: skipped")
            except Exception as exc:  # noqa: BLE001 - keep going with the other repos
                detail = getattr(exc, "stderr", "") or exc
                log(f"{label}: failed: {detail}")
                results.append(f"{label}: failed")
        cleanup_finished(state)
        caffeinate.terminate()

    log("summary: " + "; ".join(results))
    notify(f"{APP_NAME}: {group}", "; ".join(results))


@app.command()
def cleanup(
    *,
    scheduled: Annotated[
        bool, typer.Option(hidden=True, help="Started by launchd.")
    ] = False,
) -> None:
    """Remove checkouts whose pull requests are merged or closed."""
    if scheduled and is_weekend(load_config()):
        log("skipping cleanup, since it is the weekend")
        return
    try:
        with filelock.FileLock(LOCK_FILE, timeout=0):
            cleanup_finished(load_state())
    except filelock.Timeout:
        log("a run is in progress; skipping cleanup")


@app.command(name="list")
def list_groups() -> None:
    """Show which repositories fall into which group, and their prompts."""
    for name, repos in discover(load_config()).items():
        typer.echo(f"{name}:" + ("" if repos else " -"))
        for repo in repos:
            typer.echo(f"  {repo.name} ({', '.join(repo.prompts)})")


@app.command()
def status() -> None:
    """Show the schedule and the pull requests still pending."""
    config = load_config()
    loaded = set(installed_labels())
    for group in config.groups:
        mark = "loaded" if group.label in loaded else "NOT INSTALLED"
        typer.echo(f"{group.name:<10} {group.weekday:<10} {group.time:%H:%M}  {mark}")
        for prompt in config.prompts:
            typer.echo(f"  {prompt.name}: {config.cadence(group, prompt)}")
    if config.skip_weekends:
        typer.echo("scheduled jobs skip Saturdays and Sundays")
    state = load_state()
    typer.echo(f"\npending pull requests: {len(state.pending)}")
    for entry in state.pending:
        typer.echo(f"  {entry.pr_url}")
    if state.managed_clones:
        typer.echo("clones to delete after their PRs finish:")
        for path in state.managed_clones:
            typer.echo(f"  {path}")


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #

DASHBOARD_FILE = ROOT / "dashboard.html"
LOG_LINE = re.compile(r"\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\] (.*)")
RUN_FOLDER = re.compile(r"(\d{4}-\d\d-\d\d)-(\d\d)(\d\d)-(.+)")
PR_EVENT = re.compile(r"(open|merged|closed) pull request (https://\S+/pull/\d+)")
PR_FINISHED = re.compile(r"(\S+/\S+)#(\d+) is (merged|closed); cleaning up")
EXIT_EVENT = re.compile(r"agent exited with code (-?\d+)")


class Job(Strict):
    """One prompt's agent run in one repository, as read back from the logs."""

    repo: str
    prompt: str
    started: dt.datetime
    finished: dt.datetime | None = None
    exit_code: int | None = None
    pr_url: str | None = None
    pr_state: str | None = None
    # Why the job ended without a pull request: skipped, failed, or none opened.
    problem: str | None = None
    transcript: Path | None = None


class GroupRun(Strict):
    """One run of a group, scheduled or started by hand."""

    group: str
    started: dt.datetime
    finished: dt.datetime | None = None
    note: str | None = None
    jobs: list[Job] = []


def read_log(path: Path) -> list[tuple[dt.datetime, str]]:
    """The timestamped lines of a log, skipping noise from the login shell."""
    return [
        (dt.datetime.fromisoformat(match[1]), match[2])
        for line in path.read_text(errors="replace").splitlines()
        if (match := LOG_LINE.fullmatch(line))
    ]


def local_time(timestamp: float) -> dt.datetime:
    return (
        dt.datetime.fromtimestamp(timestamp, dt.UTC).astimezone().replace(tzinfo=None)
    )


def record_job_event(
    run: GroupRun, jobs: dict[str, Job], at: dt.datetime, label: str, event: str
) -> None:
    # Labels are "<repo> <prompt>"; older logs carry only "<repo>".
    repo, _, prompt = label.partition(" ")
    problem = event.startswith(("skipped: ", "failed: "))
    if event.startswith("running agent in ") or (problem and label not in jobs):
        # Resolve the transcript in LOG_DIR, which may have moved since.
        logged = Path(event.rpartition("(log: ")[2].removesuffix(")"))
        jobs[label] = Job(
            repo=repo,
            prompt=prompt,
            started=at,
            transcript=LOG_DIR / logged.parent.name / logged.name
            if logged.parent.name
            else None,
        )
        run.jobs.append(jobs[label])
    job = jobs.get(label)
    if job is None:
        return
    if code := EXIT_EVENT.fullmatch(event):
        job.exit_code, job.finished = int(code[1]), at
    elif pr := PR_EVENT.fullmatch(event):
        job.pr_state, job.pr_url = pr[1], pr[2]
    elif event.startswith("no pull request"):
        job.problem = "no pull request"
    elif problem:
        job.problem, job.finished = event, at


def parse_group_log(group: str, lines: list[tuple[dt.datetime, str]]) -> list[GroupRun]:
    runs: list[GroupRun] = []
    run: GroupRun | None = None
    jobs: dict[str, Job] = {}
    for at, message in lines:
        label, _, event = message.partition(": ")
        if label == f"group {group}":
            run = GroupRun(group=group, started=at)
            jobs = {}
            runs.append(run)
            if event == "nothing due" or event.startswith("skipped"):
                run.note, run.finished, run = event, at, None
        elif run is not None and label == "summary":
            run.finished, run = at, None
        elif run is not None:
            record_job_event(run, jobs, at, label, event)
    return runs


def manual_runs(config: Config, logged: set[Path]) -> list[GroupRun]:
    """Runs started by hand, which leave only their transcripts behind."""
    suffixes = sorted((f"-{p.name}" for p in config.prompts), key=len, reverse=True)
    runs = []
    for folder in LOG_DIR.iterdir():
        match = RUN_FOLDER.fullmatch(folder.name)
        if not folder.is_dir() or match is None or folder in logged:
            continue
        run = GroupRun(
            group=match[4],
            started=dt.datetime.fromisoformat(f"{match[1]} {match[2]}:{match[3]}"),
            note="started by hand; outcomes are not logged",
        )
        for transcript in folder.glob("*.log"):
            stem = transcript.stem
            suffix = next((s for s in suffixes if stem.endswith(s)), "")
            info = transcript.stat()
            run.jobs.append(
                Job(
                    repo=stem.removesuffix(suffix),
                    prompt=suffix.removeprefix("-"),
                    started=local_time(info.st_birthtime),
                    finished=local_time(info.st_mtime),
                    transcript=transcript,
                )
            )
        run.jobs.sort(key=lambda j: j.started)
        run.finished = max((j.finished for j in run.jobs if j.finished), default=None)
        runs.append(run)
    return runs


def collect_runs(config: Config) -> tuple[list[GroupRun], dict[str, str]]:
    """Every run in the logs, newest first, and each PR's final state by URL."""
    runs: list[GroupRun] = []
    final: dict[str, str] = {}
    running = {label.rpartition(".")[2] for label in running_jobs()}
    for path in LOG_DIR.glob("*.log") if LOG_DIR.is_dir() else []:
        lines = read_log(path)
        for _, message in lines:
            if match := PR_FINISHED.fullmatch(message):
                final[f"https://github.com/{match[1]}/pull/{match[2]}"] = match[3]
        group_runs = parse_group_log(path.stem, lines)
        for run in group_runs:
            if run.finished is None and (
                run is not group_runs[-1] or run.group not in running
            ):
                run.note = "interrupted before its summary"
        runs += group_runs
    logged = {j.transcript.parent for r in runs for j in r.jobs if j.transcript}
    if LOG_DIR.is_dir():
        runs += manual_runs(config, logged)
    for entry in load_state().pending:
        final.setdefault(entry.pr_url, "open")
    return sorted(runs, key=lambda r: r.started, reverse=True), final


def next_run(group: Group, now: dt.datetime) -> dt.datetime:
    days = (WEEKDAYS.index(group.weekday) - now.isoweekday()) % 7
    when = dt.datetime.combine(now.date() + dt.timedelta(days=days), group.time)
    return when if when > now else when + dt.timedelta(weeks=1)


def format_duration(start: dt.datetime, end: dt.datetime | None) -> str:
    if end is None:
        return "&ndash;"
    minutes, seconds = divmod(int((end - start).total_seconds()), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours} h {minutes:02} min"
    return f"{minutes} min" if minutes else f"{seconds} s"


def job_status(job: Job, final: dict[str, str]) -> tuple[str, str]:
    """A job's outcome as a (CSS class, text) chip."""
    if job.pr_url is not None:
        state = final.get(job.pr_url, job.pr_state or "open")
        return state, state
    if job.problem is not None and job.problem.startswith("failed"):
        return "failed", "failed"
    if job.exit_code not in {0, None}:
        return "failed", f"exit {job.exit_code}"
    if job.problem is not None:
        return "muted", job.problem.partition(":")[0]
    return "muted", "unknown" if job.finished else "running"


def render_job(job: Job, owner: str, final: dict[str, str]) -> str:
    esc = html.escape
    kind, text = job_status(job, final)
    status = f'<span class="chip {kind}">{esc(text)}</span>'
    if job.pr_url is not None:
        number = job.pr_url.rpartition("/")[2]
        status = f'<a href="{esc(job.pr_url)}">#{number}</a> {status}'
    transcript = (
        f'<a href="{esc(job.transcript.as_uri())}">log</a>'
        if job.transcript and job.transcript.exists()
        else ""
    )
    exit_code = "" if job.exit_code is None else str(job.exit_code)
    search = esc(f"{job.repo} {job.prompt} {text}".lower())
    repo_url = f"https://github.com/{owner}/{job.repo}"
    return (
        f'<tr data-search="{search}">'
        f'<th scope="row"><a href="{esc(repo_url)}">{esc(job.repo)}</a></th>'
        f"<td>{esc(job.prompt) or '&ndash;'}</td>"
        f"<td>{job.started:%H:%M}</td>"
        f'<td class="num">{format_duration(job.started, job.finished)}</td>'
        f'<td class="num{" bad" if exit_code not in {"", "0"} else ""}">'
        f"{exit_code}</td>"
        f"<td>{status}</td><td>{transcript}</td></tr>"
    )


def render_run(run: GroupRun, owner: str, final: dict[str, str]) -> str:
    esc = html.escape
    end = f"&ndash;{run.finished:%H:%M}" if run.finished else ""
    title = (
        f'<span class="when">{run.started:%a %d %b %Y, %H:%M}{end}</span>'
        f'<span class="group">{esc(run.group)}</span>'
    )
    note = f'<p class="note">{esc(run.note)}</p>' if run.note is not None else ""
    if not run.jobs:
        return f'<section class="run empty"><h3>{title}</h3>{note}</section>'
    rows = "".join(render_job(job, owner, final) for job in run.jobs)
    meta = (
        f"{len(run.jobs)} job{'s' * (len(run.jobs) != 1)}"
        f" · {format_duration(run.started, run.finished)}"
    )
    return (
        f'<section class="run"><h3>{title}<span class="meta">{meta}</span></h3>'
        f'{note}<div class="table-wrapper"><table>'
        "<thead><tr><th>Repository</th><th>Prompt</th><th>Started</th>"
        '<th class="num">Took</th><th class="num">Exit</th><th>Pull request</th>'
        f"<th>Transcript</th></tr></thead><tbody>{rows}</tbody></table></div>"
        "</section>"
    )


def render_dashboard(config: Config) -> str:
    esc = html.escape
    now = dt.datetime.now()
    runs, final = collect_runs(config)
    jobs = [job for run in runs for job in run.jobs]
    statuses = [job_status(job, final)[0] for job in jobs]
    tiles = [
        ("Group runs", sum(1 for run in runs if run.jobs)),
        ("Agent runs", len(jobs)),
        ("Pull requests", sum(1 for job in jobs if job.pr_url is not None)),
        ("Merged", statuses.count("merged")),
        ("Open", statuses.count("open")),
        ("Failed", statuses.count("failed")),
    ]
    stats = "".join(
        f'<div class="tile"><span class="value">{value}</span>'
        f'<span class="label">{name}</span></div>'
        for name, value in tiles
    )
    schedule = "".join(
        f"<tr><th scope='row'>{esc(group.name)}</th>"
        f"<td>{group.weekday[:3]} {group.time:%H:%M}</td>"
        f"<td>{next_run(group, now):%a %d %b, %H:%M}</td><td>"
        + ", ".join(
            f"{esc(p.name)} <span class='muted'>{config.cadence(group, p)}</span>"
            for p in config.prompts
        )
        + "</td></tr>"
        for group in sorted(config.groups, key=lambda g: next_run(g, now))
    )
    body = "".join(render_run(run, config.owner, final) for run in runs) or (
        f'<p class="note">No runs logged in {esc(str(LOG_DIR))} yet.</p>'
    )
    weekend = " Scheduled jobs skip weekends." if config.skip_weekends else ""
    return DASHBOARD_PAGE.format(
        css=DASHBOARD_CSS,
        theme=DASHBOARD_THEME,
        script=DASHBOARD_SCRIPT,
        generated=f"{now:%a %d %b %Y, %H:%M}",
        stats=stats,
        schedule=schedule,
        weekend=weekend,
        runs=body,
    )


DASHBOARD_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<script>{theme}</script>
<title>LLM Dependabot dashboard</title>
<style>{css}</style>
</head>
<body>
<header>
  <div>
    <h1>LLM Dependabot</h1>
    <p class="muted">Generated {generated} from the run logs.
    Run <code>make dashboard</code> to refresh.</p>
  </div>
  <div class="controls">
  <button id="theme" type="button">
    <span class="to-dark">Dark mode</span><span class="to-light">Light mode</span>
  </button>
  <label class="filter">
    <span class="visually-hidden">Filter jobs</span>
    <input id="filter" type="search" autocomplete="off"
      placeholder="Filter by repository, prompt, or status">
  </label>
  </div>
</header>
<main>
  <section class="tiles" aria-label="Totals">{stats}</section>
  <h2 id="schedule-caption">Schedule</h2>
  <div class="table-wrapper" tabindex="0" role="region"
    aria-labelledby="schedule-caption">
    <table>
      <thead><tr><th>Group</th><th>Runs</th><th>Next run</th><th>Prompts</th>
      </tr></thead>
      <tbody>{schedule}</tbody>
    </table>
  </div>
  <p class="muted small">Monthly prompts run at the group's first run of each
  month.{weekend}</p>
  <h2>Runs</h2>
  <div id="runs">{runs}</div>
  <p id="no-match" class="note" hidden>No jobs match the filter.</p>
</main>
<script>{script}</script>
</body>
</html>
"""

# Applies a stored light or dark override before the page renders.
DASHBOARD_THEME = """
try {
  document.querySelector('meta[name="color-scheme"]').content =
    localStorage.getItem("color-scheme") ?? "light dark";
} catch {}
"""

DASHBOARD_CSS = """
:root {
  color-scheme: light dark;
  &:has(> head > meta[name="color-scheme"][content="dark"]) { color-scheme: dark; }
  &:has(> head > meta[name="color-scheme"][content="light"]) { color-scheme: light; }
  --bg: light-dark(#faf8f4, #171512);
  --surface: light-dark(#fdfcf9, #201d19);
  --bg-alt: light-dark(#f2efe8, #2a2621);
  --text: light-dark(#201d18, #ece7dd);
  --muted: light-dark(#5d574c, #a59d8f);
  --border: light-dark(#e3ded2, #3a352e);
  --accent: light-dark(#14584d, #5fbfae);
  --accent-tint: light-dark(#e3efeb, #1d3430);
  --rust: light-dark(#9a3d2e, #e08a78);
  --rust-tint: light-dark(#f6e6e2, #3b2420);
  --serif: "Fraunces Variable", "Fraunces", ui-serif, Georgia, serif;
  --sans: "Hanken Grotesk Variable", "Hanken Grotesk", system-ui, sans-serif;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 15px/1.5 var(--sans);
}
header, main { max-inline-size: 72rem; margin-inline: auto; padding-inline: 1.5rem; }
header {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  align-items: end;
  justify-content: space-between;
  padding-block: 2rem 1rem;
  border-block-end: 1px solid var(--border);
}
h1, h2, h3 { font-family: var(--serif); font-weight: 600; margin: 0; }
h1 { font-size: 1.9rem; color: var(--accent); }
h2 { font-size: 1.25rem; margin-block: 2rem 0.75rem; }
h3 {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 0.75rem;
  align-items: baseline;
  font-size: 1rem;
}
header p { margin: 0.25rem 0 0; }
a { color: var(--accent); text-underline-offset: 2px; }
code {
  font-size: 0.9em;
  background: var(--bg-alt);
  padding: 0.05em 0.35em;
  border-radius: 4px;
}
.muted, .meta, .note { color: var(--muted); }
.small { font-size: 0.85rem; }
.note { margin: 0.25rem 0 0; font-size: 0.9rem; }
.controls { display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; }
#theme {
  padding: 0.5rem 0.75rem;
  font: inherit;
  color: inherit;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
}
#theme:hover { background: var(--bg-alt); }
#theme:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
/* The button offers the scheme opposite to the one shown. */
.to-light { display: none; }
:root:has(meta[content="dark"]) .to-light { display: inline; }
:root:has(meta[content="dark"]) .to-dark { display: none; }
@media (prefers-color-scheme: dark) {
  :root:not(:has(meta[content="light"])) .to-light { display: inline; }
  :root:not(:has(meta[content="light"])) .to-dark { display: none; }
}
.filter input {
  inline-size: min(22rem, 80vw);
  padding: 0.5rem 0.75rem;
  font: inherit;
  color: inherit;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
}
.filter input:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
  gap: 0.75rem;
  margin-block-start: 1.5rem;
}
.tile {
  display: flex;
  flex-direction: column;
  padding: 0.9rem 1rem;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
}
.tile .value { font: 600 1.7rem/1.1 var(--serif); font-variant-numeric: tabular-nums; }
.tile .label { color: var(--muted); font-size: 0.85rem; }
.table-wrapper {
  overflow-x: auto;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
}
table { inline-size: 100%; border-collapse: collapse; }
th, td { padding: 0.45rem 0.9rem; text-align: start; white-space: nowrap; }
thead th {
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--muted);
  background: var(--bg-alt);
}
tbody th { font-weight: 500; }
tbody tr + tr > * { border-block-start: 1px solid var(--border); }
td:last-child { inline-size: 100%; }
.num { text-align: end; font-variant-numeric: tabular-nums; }
.bad { color: var(--rust); }
.run { margin-block-end: 1.25rem; }
.run h3 { margin-block-end: 0.5rem; }
.run.empty h3 { margin: 0; font-size: 0.95rem; font-weight: 500; }
.run.empty { display: flex; flex-wrap: wrap; gap: 0 0.75rem; align-items: baseline; }
.run.empty .note { margin: 0; }
.group {
  font: 500 0.8rem var(--sans);
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
  background: var(--accent-tint);
  color: var(--accent);
}
.meta { font: 400 0.85rem var(--sans); }
.chip {
  display: inline-block;
  padding: 0 0.5rem;
  border-radius: 999px;
  font-size: 0.8rem;
  background: var(--bg-alt);
  color: var(--muted);
}
.chip.merged, .chip.open { background: var(--accent-tint); color: var(--accent); }
.chip.failed { background: var(--rust-tint); color: var(--rust); }
.visually-hidden {
  position: absolute;
  inline-size: 1px;
  block-size: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
main { padding-block-end: 3rem; }
"""

DASHBOARD_SCRIPT = """
const meta = document.querySelector('meta[name="color-scheme"]');
const systemDark = matchMedia("(prefers-color-scheme: dark)");
document.getElementById("theme").addEventListener("click", () => {
  const system = systemDark.matches ? "dark" : "light";
  const shown = meta.content === "light dark" ? system : meta.content;
  const target = shown === "dark" ? "light" : "dark";
  // Choosing the system's own scheme returns to following the system.
  meta.content = target === system ? "light dark" : target;
  try {
    if (target === system) localStorage.removeItem("color-scheme");
    else localStorage.setItem("color-scheme", target);
  } catch {}
});
addEventListener("storage", (event) => {
  if (event.key === "color-scheme") meta.content = event.newValue ?? "light dark";
});
const filter = document.getElementById("filter");
const runs = [...document.querySelectorAll(".run")];
filter.addEventListener("input", () => {
  const terms = filter.value.toLowerCase().split(/\\s+/).filter(Boolean);
  let shown = 0;
  for (const run of runs) {
    const rows = [...run.querySelectorAll("tr[data-search]")];
    let visible = 0;
    for (const row of rows) {
      row.hidden = !terms.every((term) => row.dataset.search.includes(term));
      visible += !row.hidden;
    }
    run.hidden = terms.length > 0 && visible === 0;
    shown += !run.hidden;
  }
  document.getElementById("no-match").hidden = shown > 0;
});
"""


@app.command()
def dashboard(
    *,
    open_browser: Annotated[
        bool, typer.Option("--open/--no-open", help="Open it in the browser.")
    ] = True,
) -> None:
    """Build an HTML dashboard of past runs and their pull requests from the logs."""
    DASHBOARD_FILE.write_text(render_dashboard(load_config()))
    typer.echo(f"wrote {DASHBOARD_FILE}")
    if open_browser:
        typer.launch(DASHBOARD_FILE.as_uri())


@app.command()
def install() -> None:
    """Build the app, then write and load the launchd agents."""
    config = load_config()
    install_agents(config)
    if not full_disk_access_granted(config.clone_root):
        show_full_disk_access_steps()
    status()


@app.command()
def uninstall() -> None:
    """Unload and remove the launchd agents."""
    for label in installed_labels():
        unload(label)
        log(f"removed {label}")


# --------------------------------------------------------------------------- #
# Interactive setup
# --------------------------------------------------------------------------- #


def step(title: str) -> None:
    typer.secho(f"\n==> {title}", bold=True)


def pause(message: str) -> None:
    typer.prompt(f"{message} Press Enter to continue", default="", show_default=False)


def ensure_brew_bundle() -> None:
    step("Homebrew packages (Brewfile)")
    if not succeeds("brew", "bundle", "check", "--no-upgrade", "--file", BREWFILE):
        fail(
            "some Brewfile packages are missing; run `make setup`, which installs them"
        )
    typer.echo("installed")


def ensure_signed_in(config: Config) -> None:
    step("GitHub CLI sign-in")
    while not succeeds("gh", "auth", "status"):
        if not typer.confirm(
            "gh is not signed in. Run `gh auth login` now?", default=True
        ):
            fail("gh must be signed in")
        interactive("gh", "auth", "login")
    typer.echo("signed in")

    agent = config.agent
    step(f"{agent.name} sign-in")
    if shutil.which(agent.command[0]) is None:
        fail(
            f"{agent.command[0]} is not installed; add its package to the Brewfile"
            " and rerun `make setup`"
        )
    if agent.check is None:
        typer.echo(f"no sign-in check configured; make sure {agent.name} is signed in")
        return
    while not succeeds(*agent.check):
        typer.echo(
            f"`{' '.join(agent.check)}` failed. Run `{agent.command[0]}` in another"
            " terminal and sign in."
        )
        pause("Once signed in, come back here.")
    typer.echo("signed in")


def check_owner(config: Config) -> None:
    step("Repository owner")
    login = sh("gh", "api", "user", "--jq", ".login")
    if login.lower() == config.owner.lower():
        typer.echo(f"{CONFIG_FILE.name} owner {config.owner!r} matches your account")
        return
    typer.echo(
        f"{CONFIG_FILE.name} names {config.owner!r}, but gh is signed in as {login!r}."
    )
    if typer.confirm(f"Set owner to {login!r} in {CONFIG_FILE.name}?", default=True):
        text = CONFIG_FILE.read_text()
        CONFIG_FILE.write_text(
            re.sub(r"^owner: .*$", f"owner: {login}", text, count=1, flags=re.MULTILINE)
        )
        config.owner = login


def ensure_clone_root(config: Config) -> None:
    step("Clone directory")
    root = config.clone_root
    if not root.is_dir():
        if not typer.confirm(f"{root} does not exist. Create it?", default=True):
            fail(f"set clone_root in {CONFIG_FILE.name} to an existing directory")
        root.mkdir(parents=True)
    typer.echo(str(root))


def choose_private_repos(config: Config) -> None:
    step("Private repositories")
    if PRIVATE_FILE.exists():
        typer.echo(
            f"{PRIVATE_FILE.name} already lists"
            f" {len(config.private_repos)} repositories"
        )
        if not typer.confirm(f"Choose them again (rewrites {PRIVATE_FILE.name})?"):
            return
    candidates = [
        item.name
        for item in owned_repos(config, "private")
        if prompts_in(item.repo(config.owner), config)
    ]
    if not candidates:
        typer.echo("no private repositories contain any of the configured prompts")
    chosen = [
        name
        for name in candidates
        if typer.confirm(f"Include private repository {name}?", default=True)
    ]
    data = {"repos": chosen}
    PRIVATE_FILE.write_text(
        "# Private repositories to include; git-ignored, never commit it.\n\n"
        + yaml.safe_dump(data, sort_keys=False)
    )
    config.private_repos = frozenset(chosen)
    typer.echo(f"wrote {PRIVATE_FILE.name} with {len(chosen)} repositories")


def install_git_hooks() -> None:
    step("Git hooks")
    if interactive("prek", "install") != 0:
        fail("prek install failed")


def ensure_full_disk_access(config: Config) -> None:
    step(f"{APP_NAME} app, launchd agents, and Full Disk Access")
    install_agents(config)
    while not full_disk_access_granted(config.clone_root):
        show_full_disk_access_steps()
        pause(f"Once {APP_NAME} is switched on,")
    typer.echo(f"scheduled jobs can read {config.clone_root}")


@app.command()
def setup() -> None:
    """Interactive first-time setup, safe to rerun.

    Checks prerequisites and sign-ins, chooses private repositories, and
    installs the git hooks, the launchd agents, and Full Disk Access.
    """
    if not os.isatty(0):
        fail("setup is interactive; run it from a terminal")
    config = load_config()
    ensure_brew_bundle()
    ensure_signed_in(config)
    check_owner(config)
    ensure_clone_root(config)
    choose_private_repos(config)
    install_git_hooks()
    ensure_full_disk_access(config)
    step("Done")
    status()
    typer.echo("\nPreview a group with `make dry-run GROUP=<group>`.")


if __name__ == "__main__":
    app()
