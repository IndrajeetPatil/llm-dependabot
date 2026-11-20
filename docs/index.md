# llm-dependabot

Dependabot, but an LLM agent does the updating.

On a weekly or monthly schedule, on your own Mac, llm-dependabot runs each
repository's committed prompts with a coding agent in YOLO mode, and the agent
opens a pull request with the changes: dependency updates by default, plus a
monthly codebase simplification. The agent and how it is called are
configurable; the default is [Antigravity CLI](https://antigravity.google)
(`agy`).
Unlike Dependabot, it can follow a project's own conventions, fix the breakage
an upgrade causes, and batch related bumps into one reviewable change.

- **Opt in per repository and prompt:** a repository takes part in each
  prompt it commits, such as `.github/prompts/update-deps.md` (weekly) or
  `.github/prompts/simplify-codebase.md` (monthly), and the prompt runs
  verbatim.

- **Staggered by ecosystem:** web projects on Monday, Python on Tuesday, other
  repositories on Wednesday, and R on the first Thursday of the month.
  Nothing runs at weekends.

- **Local only:** `launchd` starts the jobs, and the agent, `gh`, and `git` use
  the credentials already on the Mac. There is no CI and no secrets.

- **Tidy:** the agent works in a separate git worktree, and clones made just
  for a run are deleted once their pull request is merged.

![Software Giga Factory: a staggered schedule activates the software factory inside each project. Each project runs its committed prompt and project guidance through an isolated coding-agent worktree, pull request, project checks, and maintainer review, with findings returned for fixes. The groups run weekly; monthly prompts run when due, one repository and due prompt at a time.](images/giga-factory.webp)

## Quick start

On macOS with [Homebrew](https://brew.sh):

```sh
gh repo clone IndrajeetPatil/llm-dependabot ~/Documents/GitHub/llm-dependabot
cd ~/Documents/GitHub/llm-dependabot
make setup
```

`make setup` interactively installs what is missing, signs you in, asks which
private repositories to include, and walks you through granting the
**LLM Dependabot** app Full Disk Access.

## Guides

| Guide | Covers |
| --- | --- |
| [Setup](setup.md) | Requirements, `make setup`, Full Disk Access, and uninstalling |
| [Configuration](configuration.md) | `config.yaml`, `private.yaml`, prompts, and the schedule |
| [Usage](usage.md) | Everyday commands, logs, files on disk, and troubleshooting |
| [Architecture](architecture.md) | How a run works and why it is built this way |
| [Development](development.md) | Toolchain, checks, git hooks, and the hex sticker |
