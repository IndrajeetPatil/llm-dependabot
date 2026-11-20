#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.15"
# dependencies = [
#   "filelock>=4.2.12",
#   "pydantic>=2.14.3",
#   "pyyaml>=6.0.3",
#   "typer>=0.29.2",
# ]
# ///
"""Run each repository's update-deps prompt with a coding agent every week."""

import contextlib
import datetime as dt
import json
import os
import re
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal, NoReturn, get_args
lazy import hashlib
lazy import plistlib
lazy import shlex
lazy import tempfile

import typer
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveFloat,
    ValidationError,
    field_validator,
)
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
WEEKDAYS: tuple[str, ...] = get_args(Weekday.__value__)  # launchd: Sunday is 0

app = typer.Typer(
    help=__doc__,
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
)


# --------------------------------------------------------------------------- #
# Configuration and state
# --------------------------------------------------------------------------- #


class Group(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    languages: list[str]
    weekday: Weekday
    time: dt.time

    @property
    def label(self) -> str:
        return f"{BUNDLE_ID}.{self.name}"


PROMPT = "{prompt}"
TIMEOUT_HOURS = "{timeout_hours}"


class Agent(BaseModel):
    """The coding agent that runs each prompt, and how to call it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

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


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner: str
    prompt_path: str
    clone_root: Path
    agent: Agent
    agent_timeout_hours: PositiveFloat
    cleanup_interval_hours: PositiveFloat
    groups: list[Group]
    # Filled in from private.yaml, never from config.yaml.
    private_repos: frozenset[str] = Field(default=frozenset(), exclude=True)

    @field_validator("clone_root")
    @classmethod
    def _expand(cls, value: Path) -> Path:
        return value.expanduser()

    @field_validator("groups")
    @classmethod
    def _unique(cls, groups: list[Group]) -> list[Group]:
        names = [g.name for g in groups]
        if len(names) != len(set(names)):
            msg = "group names must be unique"
            raise ValueError(msg)
        return groups

    def group(self, name: str) -> Group:
        group = next((g for g in self.groups if g.name == name), None)
        if group is None:
            choices = [g.name for g in self.groups]
            fail(f"unknown group {name!r}; choose from {choices}")
        return group


class PrivateRepos(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repos: list[str] = []


class Checkout(BaseModel):
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


class State(BaseModel):
    pending: list[Pending] = []
    managed_clones: list[Path] = []


@dataclass(frozen=True, slots=True)
class Repo:
    owner: str
    name: str
    default_branch: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


class SkipRepoError(Exception):
    """A repository cannot be processed this run."""


def fail(message: str) -> NoReturn:
    typer.secho(message, err=True, fg="red")
    raise typer.Exit(1)


def load_config() -> Config:
    """Read config.yaml plus the private repository list from private.yaml."""
    try:
        config = Config.model_validate(yaml.safe_load(CONFIG_FILE.read_text()))
        private = {}
        if PRIVATE_FILE.exists():
            private = yaml.safe_load(PRIVATE_FILE.read_text()) or {}
        repos = PrivateRepos.model_validate(private).repos
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


def run_lock() -> filelock.FileLock:
    """Serialises runs and cleanups across processes."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return filelock.FileLock(LOCK_FILE)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def log(message: str) -> None:
    print(f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] {message}", flush=True)


def sh(*args: str | Path, cwd: Path | None = None, check: bool = True) -> str:
    result = subprocess.run(
        [str(a) for a in args],
        cwd=cwd,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        check=False,
    )
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, result.args, result.stdout, result.stderr
        )
    return result.stdout.strip()


def succeeds(*args: str | Path, timeout: float = 120) -> bool:
    try:
        result = subprocess.run(
            [str(a) for a in args],
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


def gh_json(*args: str) -> Any:
    return json.loads(sh("gh", *args) or "null")


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


def owned_repos(config: Config, visibility: str | None = None) -> list[dict]:
    args = ["--visibility", visibility] if visibility else []
    listing: list[dict] = gh_json(
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
    # Empty repositories have no default branch.
    return sorted(
        (item for item in listing if item["defaultBranchRef"]),
        key=lambda item: item["name"].lower(),
    )


def discover(config: Config, group: str | None = None) -> dict[str, list[Repo]]:
    """Map group name to the repositories in it that carry the prompt.

    Public repositories are included automatically; private ones only when
    private.yaml lists them.
    """
    listing = owned_repos(config)
    private = config.private_repos
    owned_private = {i["name"] for i in listing if i["visibility"] != "PUBLIC"}
    if missing := private - owned_private:
        log(f"{PRIVATE_FILE.name}: not owned private repositories: {sorted(missing)}")
    grouped: dict[str, list[Repo]] = {g.name: [] for g in config.groups}
    for item in listing:
        if item["visibility"] != "PUBLIC" and item["name"] not in private:
            continue
        language = (item["primaryLanguage"] or {}).get("name", "")
        name = group_for(language, config)
        if name is None or (group is not None and name != group):
            continue
        repo = Repo(config.owner, item["name"], item["defaultBranchRef"]["name"])
        if has_prompt(repo, config.prompt_path):
            grouped[name].append(repo)
    return grouped


# --------------------------------------------------------------------------- #
# Checkouts
# --------------------------------------------------------------------------- #


def remote_matches(clone: Path, repo: Repo) -> bool:
    url = sh("git", "-C", clone, "remote", "get-url", "origin", check=False)
    return url.lower().removesuffix(".git").endswith(repo.full_name.lower())


def prepare_checkout(
    repo: Repo, config: Config, state: State, log_path: Path
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
        worktree=WORKTREE_ROOT / f"{repo.name}-{stamp}",
        branch=f"chore/update-deps-{stamp}",
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
            log(f"deleting {clone}: it did not exist before its update-deps run")
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
                "pr", "view", str(entry.pr_number), "-R", entry.repo, "--json", "state"
            )["state"]
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
        if proc.stdin:
            with contextlib.suppress(BrokenPipeError):
                proc.stdin.write(prompt)
            proc.stdin.close()
        try:
            # Agents with a timeout of their own stop first; this stops the rest.
            return proc.wait(timeout=timeout_hours * 3600 + 600)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait()
            return -1


def find_pr(repo: Repo, branch: str, started: dt.datetime) -> dict | None:
    fields = "number,url,state,createdAt,headRefName"
    base = ["pr", "list", "-R", repo.full_name, "--state", "all", "--json", fields]
    prs: list[dict] = gh_json(*base, "--head", branch)
    if not prs:
        # The agent may have pushed to a branch of its own choosing.
        recent: list[dict] = gh_json(*base, "--author", "@me", "--limit", "20")
        prs = [
            p for p in recent if dt.datetime.fromisoformat(p["createdAt"]) >= started
        ]
    return max(prs, key=lambda p: p["number"], default=None)


def process_repo(repo: Repo, config: Config, state: State, run_dir: Path) -> str:
    checkout = prepare_checkout(repo, config, state, run_dir / f"{repo.name}.log")
    try:
        # The prompt is passed verbatim, exactly as committed in the repository.
        prompt = (checkout.worktree / config.prompt_path).read_text()
        log(f"{repo.name}: running agent in {checkout.worktree} (log: {checkout.log})")
        code = run_agent(
            config.agent,
            checkout.worktree,
            prompt,
            checkout.log,
            config.agent_timeout_hours,
        )
        log(f"{repo.name}: agent exited with code {code}")
        current = sh(
            "git", "-C", checkout.worktree, "branch", "--show-current", check=False
        )
        checkout.final_branch = current or checkout.branch
        pr = find_pr(repo, checkout.final_branch, checkout.started)
    except Exception:
        remove_checkout(checkout)
        raise

    if pr is None:
        log(f"{repo.name}: no pull request was opened; removing the worktree")
        remove_checkout(checkout)
        return f"{repo.name}: no PR (exit {code})"

    log(f"{repo.name}: {pr['state'].lower()} pull request {pr['url']}")
    state.pending.append(
        Pending(**checkout.model_dump(), pr_number=pr["number"], pr_url=pr["url"])
    )
    save_state(state)
    return f"{repo.name}: PR #{pr['number']}"


# --------------------------------------------------------------------------- #
# launchd and the LLM Dependabot app
# --------------------------------------------------------------------------- #


def launchctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["launchctl", *args], capture_output=True, text=True, check=False
    )


def gui_domain() -> str:
    return f"gui/{os.getuid()}"


def plist_for(label: str, shell_command: str, schedule: dict, log_name: str) -> dict:
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


def desired_agents(config: Config) -> dict[str, dict]:
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
            f"exec {script} run {shlex.quote(group.name)}",
            {"StartCalendarInterval": when},
            f"{group.name}.log",
        )
    label = f"{BUNDLE_ID}.cleanup"
    agents[label] = plist_for(
        label,
        f"exec {script} cleanup",
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


def app_info() -> dict:
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
    with (contents / "Info.plist").open("wb") as fh:
        plistlib.dump(app_info(), fh)
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
    with plist_path.open("wb") as fh:
        plistlib.dump(
            {
                "Label": label,
                "ProgramArguments": [str(LAUNCHER), "/bin/ls", str(path)],
                "RunAtLoad": True,
                "StandardOutPath": "/dev/null",
                "StandardErrorPath": "/dev/null",
            },
            fh,
        )
    target = f"{gui_domain()}/{label}"
    launchctl("bootout", target)
    launchctl("bootstrap", gui_domain(), str(plist_path))
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
    subprocess.run(["open", FULL_DISK_ACCESS_PANE], check=False)
    subprocess.run(["open", "-R", APP_BUNDLE], check=False)


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
        with path.open("wb") as fh:
            plistlib.dump(plist, fh)
        result = launchctl("bootstrap", gui_domain(), str(path))
        if result.returncode != 0:
            fail(f"launchctl bootstrap {label} failed: {result.stderr.strip()}")
        log(f"loaded {label}")


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #


@app.command()
def run(
    group: str,
    repo: Annotated[
        list[str] | None, typer.Option(help="Limit to this repository.")
    ] = None,
    *,
    dry_run: Annotated[bool, typer.Option(help="Only list the repositories.")] = False,
) -> None:
    """Run the update-deps prompt for every repository in GROUP."""
    config = load_config()
    config.group(group)
    repos = discover(config, group)[group]
    if repo:
        repos = [r for r in repos if r.name in repo]
    log(f"group {group}: {', '.join(r.name for r in repos) or 'no repositories'}")
    if dry_run or not repos:
        return

    with run_lock():
        # Keep the Mac awake (idle sleep) for as long as this process runs.
        caffeinate = subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])
        run_dir = LOG_DIR / f"{dt.datetime.now():%Y-%m-%d-%H%M}-{group}"
        run_dir.mkdir(parents=True, exist_ok=True)
        state = load_state()
        results = []
        for item in repos:
            try:
                results.append(process_repo(item, config, state, run_dir))
            except SkipRepoError as exc:
                log(f"{item.name}: skipped: {exc}")
                results.append(f"{item.name}: skipped")
            except Exception as exc:  # noqa: BLE001 - keep going with the other repos
                detail = getattr(exc, "stderr", "") or exc
                log(f"{item.name}: failed: {detail}")
                results.append(f"{item.name}: failed")
        cleanup_finished(state)
        caffeinate.terminate()

    log("summary: " + "; ".join(results))
    notify(f"{APP_NAME}: {group}", "; ".join(results))


@app.command()
def cleanup() -> None:
    """Remove checkouts whose pull requests are merged or closed."""
    try:
        with run_lock().acquire(timeout=0):
            cleanup_finished(load_state())
    except filelock.Timeout:
        log("a run is in progress; skipping cleanup")


@app.command(name="list")
def list_groups() -> None:
    """Show which repositories fall into which group."""
    for name, repos in discover(load_config()).items():
        typer.echo(f"{name}: {', '.join(r.name for r in repos) or '-'}")


@app.command()
def status() -> None:
    """Show the schedule and the pull requests still pending."""
    config = load_config()
    loaded = set(installed_labels())
    for group in config.groups:
        mark = "loaded" if group.label in loaded else "NOT INSTALLED"
        typer.echo(f"{group.name:<10} {group.weekday:<10} {group.time:%H:%M}  {mark}")
    state = load_state()
    typer.echo(f"\npending pull requests: {len(state.pending)}")
    for entry in state.pending:
        typer.echo(f"  {entry.pr_url}")
    if state.managed_clones:
        typer.echo("clones to delete after their PRs finish:")
        for path in state.managed_clones:
            typer.echo(f"  {path}")


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
    if not shutil.which(agent.command[0]):
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
        item["name"]
        for item in owned_repos(config, "private")
        if has_prompt(
            Repo(config.owner, item["name"], item["defaultBranchRef"]["name"]),
            config.prompt_path,
        )
    ]
    if not candidates:
        typer.echo(f"no private repositories contain {config.prompt_path}")
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
