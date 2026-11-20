# llm-dependabot <img src="docs/images/logo.png" align="right" width="240" alt="llm-dependabot hex sticker" />

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

![Software Giga Factory: a staggered schedule activates each project’s software factory. Prompts drive dependency updates, refactoring, simplification, and more; each runs in an isolated worktree, opens a pull request, and passes through project checks and maintainer review, with findings returned for fixes. Weekly group schedules, monthly prompts when due, one repository and due prompt at a time.](docs/images/giga-factory.webp)

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

## Documentation

| Guide | Covers |
| --- | --- |
| [Setup](docs/setup.md) | Requirements, `make setup`, Full Disk Access, and uninstalling |
| [Configuration](docs/configuration.md) | `config.yaml`, `private.yaml`, prompts, and the schedule |
| [Usage](docs/usage.md) | Everyday commands, logs, files on disk, and troubleshooting |
| [Architecture](docs/architecture.md) | How a run works and why it is built this way |
| [Development](docs/development.md) | Toolchain, checks, git hooks, and the hex sticker |
