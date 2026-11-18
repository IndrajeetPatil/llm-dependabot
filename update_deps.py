#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.15"
# dependencies = ["pyyaml>=6.0.3"]
# ///
"""Run each repository's update-deps prompt with Antigravity CLI on a weekly schedule.

Subcommands:
  install          write and load the launchd agents described in config.yaml
  uninstall        unload and remove those launchd agents
  list             show which repositories fall into which group
  run GROUP        run the update-deps prompt for every repository in GROUP
  cleanup          remove checkouts whose pull requests are merged or closed
  status           show the schedule and the pull requests still pending
"""

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
lazy import plistlib
lazy import shlex
lazy from collections.abc import Generator

lazy import yaml

SCRIPT = Path(__file__).resolve()
CONFIG_FILE = SCRIPT.parent / "config.yaml"
PRIVATE_FILE = SCRIPT.parent / "private.yaml"
LABEL_PREFIX = "com.indrajeetpatil.update-deps"
LAUNCH_AGENTS = Path.home() / "Library/LaunchAgents"
LOG_DIR = Path.home() / "Library/Logs/update-deps"
STATE_DIR = Path.home() / "Library/Application Support/update-deps"
STATE_FILE = STATE_DIR / "state.json"
LOCK_FILE = STATE_DIR / "lock"
WORKTREE_ROOT = Path.home() / "Library/Caches/update-deps/worktrees"
LAUNCHER_SOURCE = SCRIPT.parent / "launcher.c"
LAUNCHER = STATE_DIR / "update-deps-launcher"
FULL_DISK_ACCESS_PANE = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"
)
CATCH_ALL = "*"
FINISHED_PR_STATES = frozenset({"MERGED", "CLOSED"})
WEEKDAYS = frozendict(
    Sunday=0, Monday=1, Tuesday=2, Wednesday=3, Thursday=4, Friday=5, Saturday=6
)


class SkipRepoError(Exception):
    """A repository cannot be processed this run."""


@dataclass(frozen=True, slots=True)
class Repo:
    owner: str
    name: str
    default_branch: str
    language: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


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


def gh_json(*args: str) -> Any:
    return json.loads(sh("gh", *args) or "null")


def notify(title: str, message: str) -> None:
    script = (
        f"display notification {json.dumps(message)} with title {json.dumps(title)}"
    )
    subprocess.run(["osascript", "-e", script], check=False, capture_output=True)


def load_config() -> dict:
    """Read config.yaml plus the private repository list from private.yaml."""
    config = yaml.safe_load(CONFIG_FILE.read_text())
    names = [g["name"] for g in config["groups"]]
    if len(names) != len(set(names)):
        sys.exit(f"{CONFIG_FILE.name}: group names must be unique")
    for group in config["groups"]:
        if group["weekday"] not in WEEKDAYS:
            sys.exit(f"{CONFIG_FILE.name}: unknown weekday {group['weekday']!r}")
    private = {}
    if PRIVATE_FILE.exists():
        private = yaml.safe_load(PRIVATE_FILE.read_text()) or {}
    config["private_repos"] = frozenset(private.get("repos") or ())
    return config


def clone_root(config: dict) -> Path:
    return Path(config["clone_root"]).expanduser()


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"pending": [], "managed_clones": []}


def save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n")
    tmp.replace(STATE_FILE)


@contextlib.contextmanager
def exclusive_lock(*, wait: bool) -> Generator[bool]:
    """Serialise runs and cleanups; yields False if busy and wait is False."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open("w") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        except BlockingIOError:
            yield False
            return
        yield True


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #


def group_for(language: str, config: dict) -> str | None:
    for group in config["groups"]:
        if language in group["languages"]:
            return group["name"]
    for group in config["groups"]:
        if CATCH_ALL in group["languages"]:
            return group["name"]
    return None


def has_prompt(repo: Repo, prompt_path: str) -> bool:
    result = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{repo.full_name}/contents/{prompt_path}?ref={repo.default_branch}",
            "--silent",
        ],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def discover(config: dict, group: str | None = None) -> dict[str, list[Repo]]:
    """Map group name to the repositories in it that carry the prompt."""
    owner = config["owner"]
    listing = gh_json(
        "repo",
        "list",
        owner,
        "--source",
        "--no-archived",
        "--limit",
        "1000",
        "--json",
        "name,visibility,primaryLanguage,defaultBranchRef",
    )
    grouped: dict[str, list[Repo]] = {g["name"]: [] for g in config["groups"]}
    private = config["private_repos"]
    if missing := private - {i["name"] for i in listing if i["visibility"] != "PUBLIC"}:
        log(f"{PRIVATE_FILE.name}: not owned private repositories: {sorted(missing)}")
    for item in sorted(listing, key=lambda r: r["name"].lower()):
        if item["visibility"] != "PUBLIC" and item["name"] not in private:
            continue
        if not item["defaultBranchRef"]:
            continue  # empty repository
        language = (item["primaryLanguage"] or {}).get("name", "")
        name = group_for(language, config)
        if name is None or (group is not None and name != group):
            continue
        repo = Repo(owner, item["name"], item["defaultBranchRef"]["name"], language)
        if has_prompt(repo, config["prompt_path"]):
            grouped[name].append(repo)
    return grouped


# --------------------------------------------------------------------------- #
# Checkouts
# --------------------------------------------------------------------------- #


def remote_matches(clone: Path, repo: Repo) -> bool:
    url = sh("git", "-C", clone, "remote", "get-url", "origin", check=False)
    return url.lower().removesuffix(".git").endswith(repo.full_name.lower())


def prepare_checkout(repo: Repo, config: dict, state: dict) -> tuple[Path, Path, str]:
    """Return (clone, worktree, branch) for a fresh branch off the default branch.

    The agent works in a separate worktree so an existing clone's checked-out
    branch and uncommitted work are never touched.
    """
    clone = clone_root(config) / repo.name
    if (clone / ".git").exists():
        if not remote_matches(clone, repo):
            raise SkipRepoError(f"{clone} is a clone of a different repository")
    elif clone.exists():
        raise SkipRepoError(f"{clone} exists but is not a git clone")
    else:
        log(f"{repo.name}: no local copy, cloning into {clone}")
        sh("gh", "repo", "clone", repo.full_name, clone, "--", "--quiet")
        state["managed_clones"].append(str(clone))
        save_state(state)

    sh("git", "-C", clone, "fetch", "--prune", "--quiet", "origin")
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    branch = f"chore/update-deps-{stamp}"
    worktree = WORKTREE_ROOT / f"{repo.name}-{stamp}"
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
        branch,
        worktree,
        f"origin/{repo.default_branch}",
    )
    return clone, worktree, branch


def remove_checkout(entry: dict) -> None:
    clone, worktree = Path(entry["clone"]), Path(entry["worktree"])
    if not clone.exists():
        return
    if worktree.exists():
        sh("git", "-C", clone, "worktree", "remove", "--force", worktree, check=False)
    sh("git", "-C", clone, "worktree", "prune", check=False)
    for branch in {entry["branch"], entry.get("final_branch") or entry["branch"]}:
        sh("git", "-C", clone, "branch", "-D", branch, check=False)


def clone_is_disposable(clone: Path) -> tuple[bool, str]:
    if sh("git", "-C", clone, "status", "--porcelain", check=False):
        return False, "has uncommitted changes"
    worktrees = sh("git", "-C", clone, "worktree", "list", "--porcelain", check=False)
    if worktrees.count("worktree ") > 1:
        return False, "has other worktrees"
    unpushed = sh(
        "git",
        "-C",
        clone,
        "log",
        "--branches",
        "--not",
        "--remotes",
        "--oneline",
        check=False,
    )
    if unpushed:
        return False, "has local commits that are not on the remote"
    return True, ""


def delete_unused_managed_clones(state: dict) -> None:
    """Delete clones this tool created once no pending pull request needs them."""
    in_use = {entry["clone"] for entry in state["pending"]}
    kept = []
    for path in state["managed_clones"]:
        clone = Path(path)
        if path in in_use:
            kept.append(path)
            continue
        if not clone.exists():
            continue
        disposable, reason = clone_is_disposable(clone)
        if disposable:
            log(f"deleting {clone}: it did not exist before its update-deps run")
            shutil.rmtree(clone)
        else:
            log(f"keeping {clone} for now: it {reason}")
            kept.append(path)
    state["managed_clones"] = kept
    save_state(state)


# --------------------------------------------------------------------------- #
# Agent run
# --------------------------------------------------------------------------- #


def run_agent(worktree: Path, prompt: str, log_path: Path, timeout_hours: float) -> int:
    command = [
        "agy",
        "--dangerously-skip-permissions",
        "--print-timeout",
        f"{timeout_hours}h",
        "-p",
        prompt,
    ]
    with log_path.open("w") as out:
        proc = subprocess.Popen(
            command,
            cwd=worktree,
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            # Backstop in case the CLI's own --print-timeout does not fire.
            return proc.wait(timeout=timeout_hours * 3600 + 600)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait()
            return -1


def find_pr(repo: Repo, branch: str, started: dt.datetime) -> dict | None:
    fields = "number,url,state,createdAt,headRefName"
    prs: list[dict] = gh_json(
        "pr",
        "list",
        "-R",
        repo.full_name,
        "--state",
        "all",
        "--head",
        branch,
        "--json",
        fields,
    )
    if not prs:
        # The agent may have pushed to a branch of its own choosing.
        recent = gh_json(
            "pr",
            "list",
            "-R",
            repo.full_name,
            "--state",
            "all",
            "--author",
            "@me",
            "--limit",
            "20",
            "--json",
            fields,
        )
        prs = [
            p for p in recent if dt.datetime.fromisoformat(p["createdAt"]) >= started
        ]
    return max(prs, key=lambda p: p["number"], default=None)


def process_repo(repo: Repo, config: dict, state: dict, run_dir: Path) -> str:
    clone, worktree, branch = prepare_checkout(repo, config, state)
    log_path = run_dir / f"{repo.name}.log"
    started = dt.datetime.now(dt.UTC).replace(microsecond=0)
    entry = {
        "repo": repo.full_name,
        "clone": str(clone),
        "worktree": str(worktree),
        "branch": branch,
        "log": str(log_path),
        "started": started.isoformat(),
    }
    try:
        # The prompt is passed verbatim, exactly as committed in the repository.
        prompt = (worktree / config["prompt_path"]).read_text()
        log(f"{repo.name}: running agent in {worktree} (log: {log_path})")
        code = run_agent(worktree, prompt, log_path, config["agent_timeout_hours"])
        log(f"{repo.name}: agent exited with code {code}")
        final_branch = sh(
            "git", "-C", worktree, "branch", "--show-current", check=False
        )
        entry["final_branch"] = final_branch or branch
        pr = find_pr(repo, entry["final_branch"], started)
    except Exception:
        remove_checkout(entry)
        raise

    if pr is None:
        log(f"{repo.name}: no pull request was opened; removing the worktree")
        remove_checkout(entry)
        return f"{repo.name}: no PR (exit {code})"

    log(f"{repo.name}: {pr['state'].lower()} pull request {pr['url']}")
    state["pending"].append(entry | {"pr_number": pr["number"], "pr_url": pr["url"]})
    save_state(state)
    return f"{repo.name}: PR #{pr['number']}"


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #


def cmd_run(args: argparse.Namespace) -> None:
    config = load_config()
    if args.group not in {g["name"] for g in config["groups"]}:
        sys.exit(f"unknown group {args.group!r}")

    repos = discover(config, args.group)[args.group]
    if args.repo:
        repos = [r for r in repos if r.name in args.repo]
    log(f"group {args.group}: {', '.join(r.name for r in repos) or 'no repositories'}")
    if args.dry_run or not repos:
        return

    with exclusive_lock(wait=True):
        # Keep the Mac awake (idle sleep) for as long as this process runs.
        caffeinate = subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])
        run_dir = LOG_DIR / f"{dt.datetime.now():%Y-%m-%d-%H%M}-{args.group}"
        run_dir.mkdir(parents=True, exist_ok=True)
        state = load_state()
        results = []
        for repo in repos:
            try:
                results.append(process_repo(repo, config, state, run_dir))
            except SkipRepoError as exc:
                log(f"{repo.name}: skipped: {exc}")
                results.append(f"{repo.name}: skipped")
            except Exception as exc:  # noqa: BLE001 - keep going with the other repos
                detail = getattr(exc, "stderr", "") or exc
                log(f"{repo.name}: failed: {detail}")
                results.append(f"{repo.name}: failed")
        cleanup(state)
        caffeinate.terminate()

    log("summary: " + "; ".join(results))
    notify(f"update-deps: {args.group}", "; ".join(results))


def cleanup(state: dict) -> None:
    remaining = []
    for entry in state["pending"]:
        pr_ref = f"{entry['repo']}#{entry['pr_number']}"
        try:
            pr_state = gh_json(
                "pr",
                "view",
                str(entry["pr_number"]),
                "-R",
                entry["repo"],
                "--json",
                "state",
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
    state["pending"] = remaining
    save_state(state)
    delete_unused_managed_clones(state)


def cmd_cleanup(_: argparse.Namespace) -> None:
    with exclusive_lock(wait=False) as acquired:
        if not acquired:
            log("a run is in progress; skipping cleanup")
            return
        cleanup(load_state())


def plist_for(label: str, shell_command: str, schedule: dict, log_name: str) -> dict:
    return {
        "Label": label,
        # The launcher holds the Full Disk Access grant (see launcher.c). A
        # login, interactive zsh picks up the same PATH (Homebrew, uv, pnpm,
        # agy, gh) and keychain-backed credentials as a terminal session.
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


def desired_agents(config: dict) -> dict[str, dict]:
    script = shlex.quote(str(SCRIPT))
    agents = {}
    for group in config["groups"]:
        hour, minute = (int(x) for x in group["time"].split(":"))
        label = f"{LABEL_PREFIX}.{group['name']}"
        when = {"Weekday": WEEKDAYS[group["weekday"]], "Hour": hour, "Minute": minute}
        agents[label] = plist_for(
            label,
            f"exec {script} run {shlex.quote(group['name'])}",
            {"StartCalendarInterval": when},
            f"{group['name']}.log",
        )
    label = f"{LABEL_PREFIX}.cleanup"
    agents[label] = plist_for(
        label,
        f"exec {script} cleanup",
        {
            "StartInterval": int(config["cleanup_interval_hours"] * 3600),
            "RunAtLoad": True,
        },
        "cleanup.log",
    )
    return agents


def launchctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["launchctl", *args], capture_output=True, text=True, check=False
    )


def unload(label: str) -> None:
    launchctl("bootout", f"gui/{os.getuid()}/{label}")
    (LAUNCH_AGENTS / f"{label}.plist").unlink(missing_ok=True)


def installed_labels() -> list[str]:
    return sorted(p.stem for p in LAUNCH_AGENTS.glob(f"{LABEL_PREFIX}.*.plist"))


def build_launcher() -> bool:
    """Compile the launcher; return True if it changed and needs a new grant.

    macOS ties the Full Disk Access grant to the binary's code signature, so
    it is rebuilt only when launcher.c changes.
    """
    digest = hashlib.sha256(LAUNCHER_SOURCE.read_bytes()).hexdigest()
    stamp = LAUNCHER.with_suffix(".sha256")
    if LAUNCHER.exists() and stamp.exists() and stamp.read_text() == digest:
        return False
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    sh("clang", "-O2", "-Wall", "-Werror", "-o", LAUNCHER, LAUNCHER_SOURCE)
    stamp.write_text(digest)
    return True


def cmd_install(_: argparse.Namespace) -> None:
    config = load_config()
    agents = desired_agents(config)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if build_launcher():
        log(f"built {LAUNCHER}")
        print(
            "\nOne-time step: add the launcher to System Settings > Privacy &"
            " Security > Full Disk Access (press Cmd-Shift-G in the file dialog"
            f" and paste the path below), so jobs can read your clones:\n  {LAUNCHER}\n"
        )
        subprocess.run(["open", FULL_DISK_ACCESS_PANE], check=False)
        subprocess.run(["open", "-R", LAUNCHER], check=False)
    for label in installed_labels():
        unload(label)
    for label, plist in agents.items():
        path = LAUNCH_AGENTS / f"{label}.plist"
        with path.open("wb") as fh:
            plistlib.dump(plist, fh)
        result = launchctl("bootstrap", f"gui/{os.getuid()}", str(path))
        if result.returncode != 0:
            sys.exit(f"launchctl bootstrap {label} failed: {result.stderr.strip()}")
        log(f"loaded {label}")
    cmd_status(_)


def cmd_uninstall(_: argparse.Namespace) -> None:
    for label in installed_labels():
        unload(label)
        log(f"removed {label}")


def cmd_list(_: argparse.Namespace) -> None:
    config = load_config()
    for name, repos in discover(config).items():
        print(f"{name}: {', '.join(r.name for r in repos) or '-'}")


def cmd_status(_: argparse.Namespace) -> None:
    config = load_config()
    loaded = set(installed_labels())
    for group in config["groups"]:
        label = f"{LABEL_PREFIX}.{group['name']}"
        mark = "loaded" if label in loaded else "NOT INSTALLED"
        print(f"{group['name']:<10} {group['weekday']:<10} {group['time']}  {mark}")
    state = load_state()
    print(f"\npending pull requests: {len(state['pending'])}")
    for entry in state["pending"]:
        print(f"  {entry['pr_url']}")
    if state["managed_clones"]:
        print("clones to delete after their PRs finish:")
        for path in state["managed_clones"]:
            print(f"  {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(required=True)
    sub.add_parser("install").set_defaults(func=cmd_install)
    sub.add_parser("uninstall").set_defaults(func=cmd_uninstall)
    sub.add_parser("list").set_defaults(func=cmd_list)
    sub.add_parser("status").set_defaults(func=cmd_status)
    sub.add_parser("cleanup").set_defaults(func=cmd_cleanup)
    run = sub.add_parser("run")
    run.add_argument("group")
    run.add_argument("--repo", action="append", help="limit to this repository")
    run.add_argument("--dry-run", action="store_true", help="only list repositories")
    run.set_defaults(func=cmd_run)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
