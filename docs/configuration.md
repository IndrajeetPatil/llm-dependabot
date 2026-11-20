# Configuration

Two YAML files sit next to the script, and every command reads both. Both are
validated on load, so a typo fails with a clear message instead of a silent
misconfiguration.

| File | Committed | Contents |
| --- | --- | --- |
| [`config.yaml`](../config.yaml) | yes | Owner, prompt path, clone directory, coding agent, timeouts, and the schedule |
| `private.yaml` | no (git-ignored) | Private repositories to include, by name |

Run `make install` after editing either file.

## `config.yaml`

| Key | Meaning |
| --- | --- |
| `owner` | GitHub account whose repositories are considered |
| `prompt_path` | Path of the prompt inside each repository |
| `clone_root` | Where existing clones are found and missing ones are cloned |
| `agent` | The coding agent and how to call it (see below) |
| `agent_timeout_hours` | Upper bound for one repository's agent run |
| `cleanup_interval_hours` | How often finished pull requests are cleaned up |
| `groups` | The weekly schedule (see below) |

## The coding agent

The agent runs once per repository, unattended, inside a fresh worktree. The
default is Antigravity CLI in YOLO mode:

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

Any agent with a non-interactive mode works. It must be able to edit files,
run commands, and push without asking, since nobody is there to approve. For
example (check the flags against your agent's version):

| Agent | `command` | `check` |
| --- | --- | --- |
| Claude Code | `[claude, --dangerously-skip-permissions, -p, "{prompt}"]` | `[claude, auth, status]` |
| Codex CLI | `[codex, exec, --dangerously-bypass-approvals-and-sandbox, "{prompt}"]` | `[codex, login, status]` |
| GitHub Copilot CLI | `[copilot, --yolo, -p, "{prompt}"]` | — |

When switching agents, also replace `antigravity-cli` in the
[`Brewfile`](../Brewfile) with your agent's package. A run that outlasts
`agent_timeout_hours` by ten minutes is stopped, so agents without a timeout
of their own are bounded too.

## Groups and the schedule

![Configured project groups and weekly cadence: R packages run Monday at 11:00, other/default projects Tuesday at 11:00, Python projects Wednesday at 14:30, and Astro and TypeScript web applications Thursday at 11:00 local time; cleanup removes local worktrees and branches after pull requests are merged or closed.](images/ecosystem-schedule.webp)

The figure shows every configured group and its weekly schedule, including
groups with no current repository assignments. The table below lists the
language matches for each group.

Each group runs once a week at a local wall-clock time:

```yaml
groups:
  - name: python
    languages: [Python]
    weekday: Wednesday
    time: "14:30"
```

A repository joins the first group whose `languages` include its GitHub
primary language. The group with `languages: ["*"]` takes everything else.
The default schedule:

| Group | Languages | When |
| --- | --- | --- |
| `r` | R | Monday 11:00 |
| `workflows` | anything not matched by another group | Tuesday 11:00 |
| `python` | Python | Wednesday 14:30 |
| `web` | TypeScript, JavaScript, Astro, Svelte, Vue, HTML, and CSS | Thursday 11:00 |

## Which repositories take part

- **Public:** every non-archived, non-fork public repository owned by `owner`
  that contains the prompt, found automatically at run time.

- **Private:** only those listed in `private.yaml`, so their names never reach
  version control. Each still needs the prompt.

A repository that gains the prompt joins its group the following week.
`make list` shows the current assignment.

## `private.yaml`

`make setup` writes it for you. To edit it by hand, copy
[`private.example.yaml`](../private.example.yaml):

```yaml
repos:
  - my-private-app
  - another-private-tool
```

Without `private.yaml`, only public repositories run. A git hook rejects any
commit that adds this file or names one of its repositories.
