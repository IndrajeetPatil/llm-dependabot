# Architecture

llm-dependabot is a scheduler, not an agent. It decides when, where, and which prompt
the agent runs, isolates its work, and cleans up afterwards. The intelligence
lives in each repository's own prompts.

![Execution lifecycle and isolation: three bands show the Full Disk Access process boundary, safe Git worktree isolation, and coordinated pull-request tracking and cleanup.](images/execution-lifecycle.webp)

## Components

| Component | Role |
| --- | --- |
| [`llm_dependabot.py`](../llm_dependabot.py) | The CLI: a single-file uv script that discovers repositories, runs the agent, tracks pull requests, and writes the launchd agents |
| [`config.yaml`](../config.yaml) and `private.yaml` | The prompts, their cadences, the schedule, and which repositories take part (see [Configuration](configuration.md)) |
| [`app/`](../app) | Sources of the LLM Dependabot app, a tiny launcher that holds the Full Disk Access grant |
| launchd | macOS's built-in scheduler: one agent per group, plus a cleanup agent |
| Coding agent | Runs the prompt and opens the pull request; Antigravity CLI (`agy`) by default, configurable in `config.yaml` |
| `gh` and `git` | Discovery, cloning, worktrees, and pull request state |

The script leans on widely used libraries rather than code of its own:
[Typer](https://typer.tiangolo.com) for the command line and prompts,
[pydantic](https://docs.pydantic.dev) (with its Rust core) to validate the
configuration and state, [PyYAML](https://pyyaml.org) to read the YAML, and
[filelock](https://py-filelock.readthedocs.io) to serialise runs.

## Process tree

![Process and run: launchd starts the app, login shell, update scheduler, and coding agent; each repository gets a Git worktree, and the run records a pull request or removes the worktree.](images/process-and-run.webp)

- **The app** starts the job as a child process rather than replacing itself,
  so macOS treats it as the "responsible process" and applies its Full Disk
  Access grant to everything below it.

- **A login, interactive zsh** gives the job the same `PATH` and
  keychain-backed credentials as a terminal session, so nothing is configured
  through environment variables.

## A run

- **Discovery** lists the owner's repositories with `gh` and checks each for
  the configured prompts through the GitHub API, so repositories need not be
  cloned first.

- **Cadence:** a run takes every weekly prompt a repository has, plus each
  monthly one that has not yet run there this calendar month, according to
  the last runs recorded in `state.json`. Launchd starts every group weekly;
  the script decides what is due, so a missed monthly run catches up the
  following week.

- **Isolation:** each prompt runs in its own git worktree and branch, so an
  existing clone's checked-out branch and uncommitted work are never touched,
  and each prompt opens its own pull request.

- **Pull request detection** looks for a pull request from the run's branch,
  falling back to one opened by you since the run started, in case the agent
  chose its own branch name.

- **Repositories and prompts run one after another.** A failure in one is
  logged, and the run moves on. A failed run is not recorded, so it is
  retried at the next scheduled run.

- **Weekends:** with `skip_weekends`, scheduled runs and cleanups started on a
  Saturday or Sunday exit without doing anything.

- **A timeout** bounds each agent run, backed by a hard stop in case the CLI's
  own timeout does not fire.

## Cleanup

A clone that did not exist before the run is deleted once its pull request is
merged or closed. It is kept, and retried at the next cleanup, if it has
uncommitted changes, other worktrees, or unpushed commits.

## State

`state.json` records pending pull requests (with their worktree and branch),
the clones llm-dependabot created, and the date each prompt last ran in each
repository. It is written atomically, and a lock
keeps a scheduled run and a cleanup from changing it at the same time.
