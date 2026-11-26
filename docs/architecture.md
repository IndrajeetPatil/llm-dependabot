# Architecture

llm-dependabot is a scheduler, not an agent. It decides when, where, and
which prompt the agent runs, isolates its work, and cleans up afterwards. The
intelligence lives in each repository's own prompts.

![How llm-dependabot works: launchd starts the app and login shell; repository discovery finds committed prompts and those due to run, then each due prompt gets its own worktree, agent run, pull request, and cleanup.](images/architecture-overview.webp)

![Execution lifecycle and isolation: three bands show the Full Disk Access process boundary, safe Git worktree isolation, and coordinated pull-request tracking and cleanup.](images/execution-lifecycle.webp)

## Components

| Component | Role |
| --- | --- |
| `src/llm_dependabot/` | The CLI: a Python package, run with `uv run` from the checkout, that discovers repositories, runs the agent, tracks pull requests, and writes the launchd agents |
| [`config.yaml`](https://github.com/IndrajeetPatil/llm-dependabot/blob/main/config.yaml) and `private.yaml` | The prompts, their cadences, the schedule, and which repositories take part (see [Configuration](configuration.md)) |
| [`app/`](https://github.com/IndrajeetPatil/llm-dependabot/tree/main/app) | Sources of the LLM Dependabot app, a tiny launcher that holds the Full Disk Access grant |
| launchd | macOS's built-in scheduler: one agent per group, plus a cleanup agent |
| Coding agent | Runs the prompt and opens the pull request; any agent with a non-interactive mode, set in `config.yaml` |
| `gh` and `git` | Discovery, cloning, worktrees, and pull request state |

The CLI leans on widely used libraries rather than code of its own:
[Typer](https://typer.tiangolo.com) for the command line and prompts,
[pydantic](https://docs.pydantic.dev) (with its Rust core) to strictly
validate the configuration, state, and `gh` output, [PyYAML](https://pyyaml.org) to read the YAML, and
[filelock](https://py-filelock.readthedocs.io) to serialise runs.

## Process tree

```mermaid
flowchart LR
    launchd[launchd] --> app[LLM Dependabot app<br/>Full Disk Access]
    app --> shell[Login zsh<br/>PATH and keychain]
    shell --> cli[uv run llm-dependabot]
    cli --> agent[Coding agent<br/>in Git worktree]
    cli --> awake[caffeinate<br/>keeps Mac awake]
```

- **The app** starts the job as a child process rather than replacing itself,
  so macOS treats it as the "responsible process" and applies its Full Disk
  Access grant to everything below it.

- **A login, interactive zsh** gives the job the same `PATH` and
  keychain-backed credentials as a terminal session, so nothing is configured
  through environment variables.

## A run

```mermaid
flowchart TD
    discover[Discover repository and prompts] --> due{Prompt due?}
    due -- No --> skip[Skip]
    due -- Yes --> copy{Project copy exists?}
    copy -- Yes --> existing[Update existing copy]
    copy -- No --> prepare[Prepare new copy]
    existing --> worktree[Create Git worktree]
    prepare --> worktree
    worktree --> run[Run coding agent with a time limit]
    run -. Pull requests are labelled while the agent works .-> pr
    run --> success{Agent exited successfully?}
    success -- No --> failed[Log failure; prompt remains due]
    success -- Yes --> pr{Pull request opened?}
    pr -- Yes --> pending[Record pending state]
    pr -- No --> remove[Remove worktree]
    pending --> date[Record run date]
    remove --> date
    date -. Every completed run counts towards the cadence .-> cadence[Next due check]
```

- **Discovery** lists the owner's repositories with `gh` and checks each for
  the configured prompts through the GitHub API, so repositories need not be
  cloned first.

- **Cadence:** a run takes every weekly prompt a repository has, plus each
  monthly one that has not yet run there this calendar month, according to
  the last runs recorded in `state.json`. Launchd starts every group weekly;
  the CLI decides what is due, so a missed monthly run catches up the
  following week.

- **Isolation:** each prompt runs in its own git worktree and branch, so an
  existing clone's checked-out branch and uncommitted work are never touched,
  and each prompt opens its own pull request.

- **Pull request detection** looks for a pull request from the run's branch,
  falling back to one opened by you since the run started, in case the agent
  chose its own branch name. It checks every few minutes while the agent
  works, so the pull request is labelled as soon as it opens, even if the
  agent keeps working on it for hours; the check once the agent exits labels
  any pull request still unlabelled.

- **Repositories and prompts run one after another.** A failure in one is
  logged, and the run moves on. Only an agent that exits successfully counts
  towards its cadence, including one that needs no pull request. Failed and
  timed-out agents remain due, even if they opened a pull request.

- **Weekends:** with `skip_weekends`, scheduled runs and cleanups started on a
  Saturday or Sunday exit without doing anything.

- **A timeout** bounds each agent run, backed by a hard stop in case the CLI's
  own timeout does not fire. The runner sends `SIGTERM`, waits up to 30
  seconds, then sends `SIGKILL` to any remaining processes in the agent's group.

## Cleanup

Cleanup runs at the end of every run and on its own schedule. Once a pull
request is merged or closed, its worktree and local branch are removed. A
clone that did not exist before the run is then deleted, unless it has
uncommitted changes, other worktrees, or unpushed commits; it is kept and
retried at the next cleanup. A scheduled cleanup that finds a run in progress
skips that turn.

## State

`state.json` records pending pull requests (with their worktree and branch),
the clones llm-dependabot created, and the date each prompt last ran in each
repository. It also records recovery checkouts before starting their agents;
failed or interrupted runs, and runs whose pull request lookup fails, retain
these checkouts for manual recovery. `make status` lists their paths and logs,
and cleanup keeps their managed clones. See [Recovery](usage.md#recovering-a-failed-run).
It is written atomically, and a lock
keeps a scheduled run and a cleanup from changing it at the same time.
