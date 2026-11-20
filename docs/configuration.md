# Configuration

Two YAML files sit next to the script, and every command reads both. Both are
validated on load, so a typo fails with a clear message instead of a silent
misconfiguration.

| File | Committed | Contents |
| --- | --- | --- |
| [`config.yaml`](https://github.com/IndrajeetPatil/llm-dependabot/blob/main/config.yaml) | yes | Owner, prompts and their cadences, clone directory, coding agent, timeouts, and the schedule |
| `private.yaml` | no (git-ignored) | Private repositories to include, by name |

Run `make install` after editing either file.

## `config.yaml`

| Key | Meaning |
| --- | --- |
| `owner` | GitHub account whose repositories are considered |
| `prompts` | The prompts repositories can opt into, and how often each runs (see below) |
| `clone_root` | Where existing clones are found and missing ones are cloned |
| `agent` | The coding agent and how to call it (see below) |
| `agent_timeout_hours` | Upper bound for one repository's agent run |
| `cleanup_interval_hours` | How often finished pull requests are cleaned up |
| `skip_weekends` | Whether scheduled jobs do nothing on Saturdays and Sundays (default `true`) |
| `groups` | The schedule (see below) |

## The coding agent

The agent runs once per repository and prompt, unattended, inside a fresh
worktree. Any agent with a non-interactive mode works; the shipped
`config.yaml` uses Antigravity CLI:

```yaml
agent:
  name: Antigravity CLI
  command:
    - agy
    - --dangerously-skip-permissions
    - --print-timeout
    - "{timeout_hours}h"
    - -p
    - "{prompt}"
  check: [agy, models]
```

| Key | Meaning |
| --- | --- |
| `name` | Shown by `make setup` |
| `command` | The command line, one argument per item. An argument that is exactly `"{prompt}"` becomes the prompt's text; without one, the prompt goes to standard input. `{timeout_hours}` becomes `agent_timeout_hours`. |
| `check` | Optional: a command that succeeds once the agent is installed and signed in. `make setup` waits for it. |

> [!WARNING]
> Nobody is there to approve the agent's actions, so it must be able to edit
> files, run commands, and push without asking. Give it the same trust you
> give your own terminal session.

Each agent takes the same shape:

| Agent | `command` | `check` |
| --- | --- | --- |
| Antigravity CLI | `[agy, --dangerously-skip-permissions, --print-timeout, "{timeout_hours}h", -p, "{prompt}"]` | `[agy, models]` |
| Claude Code | `[claude, --dangerously-skip-permissions, -p, "{prompt}"]` | `[claude, auth, status]` |
| Codex CLI | `[codex, exec, --dangerously-bypass-approvals-and-sandbox, "{prompt}"]` | `[codex, login, status]` |
| GitHub Copilot CLI | `[copilot, --yolo, -p, "{prompt}"]` | — |

> [!TIP]
> Check the flags against your agent's version; they change between releases.

When switching agents, also replace `antigravity-cli` in the
[`Brewfile`](https://github.com/IndrajeetPatil/llm-dependabot/blob/main/Brewfile) with your agent's package. A run that outlasts
`agent_timeout_hours` by ten minutes is stopped, so agents without a timeout
of their own are bounded too.

## Prompts and cadence

Each prompt is a file that repositories opt into by committing it at `path`.
It runs verbatim, in its own worktree and branch (`chore/<name>-<timestamp>`),
so each prompt opens its own pull request.

```yaml
prompts:
  - name: update-deps
    path: .github/prompts/update-deps.md
    cadence: weekly

  - name: simplify-codebase
    path: .github/prompts/simplify-codebase.md
    cadence: monthly
```

| Key | Meaning |
| --- | --- |
| `name` | Identifies the prompt in `cadence` overrides, branch names, logs, and `make run PROMPT=…`; letters, digits, `.`, `_`, and `-` only |
| `path` | Path of the prompt inside each repository |
| `cadence` | `weekly` (the default) or `monthly`; a group can override it |

- **Weekly** prompts run at every scheduled run of the repository's group.

- **Monthly** prompts run at the group's first scheduled run in each calendar
  month. `state.json` records when each prompt last ran in each repository,
  so a monthly prompt whose run was missed, skipped, or failed runs at the
  group's next scheduled run instead of waiting a month.

![One schedule, multiple prompts: each due repository prompt gets its own Git worktree and branch, coding-agent run, and pull request, processed one at a time.](images/multiple-prompts.webp)

## Groups and the schedule

Each group runs at a local wall-clock time on one weekday, and may override a
prompt's cadence:

```yaml
groups:
  - name: r
    languages: [R]
    weekday: Thursday
    time: "11:00"
    cadence:
      update-deps: monthly
```

A repository joins the first group whose `languages` include its GitHub
primary language. The group with `languages: ["*"]` takes everything else.
The default schedule, with nothing on Fridays or at weekends:

| Group | Languages | Day | `update-deps` | `simplify-codebase` |
| --- | --- | --- | --- | --- |
| `web` | TypeScript, JavaScript, Astro, Svelte, Vue, HTML, and CSS | Monday 11:00 | weekly | first Monday of the month |
| `python` | Python | Tuesday 11:00 | weekly | first Tuesday of the month |
| `workflows` | anything not matched by another group | Wednesday 11:00 | weekly | first Wednesday of the month |
| `r` | R | Thursday 11:00 | first Thursday of the month | first Thursday of the month |

![Configured project groups and prompt cadence: Web Applications run Monday at 11:00, Python Tuesday at 11:00, Sundry Wednesday at 11:00, and R Packages Thursday at 11:00; weekly and monthly prompt cadence is shown for each group, followed by pull-request cleanup.](images/ecosystem-schedule.webp)

With `skip_weekends: true`, groups cannot be scheduled on a Saturday or
Sunday, and a scheduled job that launchd starts late at a weekend (for
example, after the Mac wakes) does nothing. Weekly prompts then wait for the
following week, and monthly ones for the group's next scheduled run.

## Which repositories take part

- **Public:** every non-archived, non-fork public repository owned by `owner`
  that contains at least one of the prompts, found automatically at run time.

- **Private:** only those listed in `private.yaml`, so their names never reach
  version control. Each still needs at least one of the prompts.

A repository runs only the prompts it contains. One that gains a prompt picks
it up at its group's next scheduled run that finds the prompt due.
`make list` shows the current assignment.

## `private.yaml`

`make setup` writes it for you. To edit it by hand, copy
[`private.example.yaml`](https://github.com/IndrajeetPatil/llm-dependabot/blob/main/private.example.yaml):

```yaml
repos:
  - my-private-app
  - another-private-tool
```

Without `private.yaml`, only public repositories run. A git hook rejects any
commit that adds this file or names one of its repositories.
