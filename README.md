# llm-dependabot <img src="https://raw.githubusercontent.com/IndrajeetPatil/llm-dependabot/main/docs/images/logo.png" align="right" width="240" alt="llm-dependabot hex sticker" />

A template for your own software giga factory: schedule repository-owned
prompts across your projects, and let a coding agent turn maintenance work
into pull requests for you to review.

## The problem

Every package, project, and application you maintain ages on its own:

- **Dependencies fall behind,** and each upgrade can break something that
  then needs fixing by hand.

- **Vulnerabilities keep appearing,** in more dependencies, more often, and
  each needs an upgrade before it can be closed.

- **New features go unused.** Newer releases of your dependencies often make
  your own code simpler, but with little time to spare, those improvements
  are never adopted.

Bots like Dependabot bump version numbers, but they cannot fix the breakage
an upgrade causes or rewrite code to use what the new version offers. The
more repositories you maintain, the further this work falls behind.

## The solution

llm-dependabot coordinates a software factory in each of your projects.
Each repository commits
prompts describing its own maintenance (updating dependencies, simplifying
the codebase, or anything else), and on a schedule, llm-dependabot runs each
due prompt with the agent. The agent opens a pull request, which goes through
the project's own checks and your review like any other.

The giga factory is the layer coordinating those project-level factories:
it decides which repositories and prompts are due, prepares isolated
worktrees, and invokes your chosen agent. Dependency updates are one use
case; repository-owned prompts can also cover refactoring, documentation,
or other repeatable work. The prompts define the work, and each project
provides its own instructions, checks, and review process.

- **Opt in per repository and prompt:** a repository takes part in each
  prompt it commits, such as `.github/prompts/update-deps.md` or
  `.github/prompts/simplify-codebase.md`, and the prompt runs verbatim.

- **A staggered schedule:** repositories are grouped by ecosystem, each group
  runs on its own weekday, and each prompt runs weekly or monthly.

- **Isolated and tidy:** every prompt runs in its own git worktree and branch,
  and clones made just for a run are deleted once their pull request is
  merged or closed.

- **Your machine, your credentials:** the agent, `gh`, and `git` use the
  sign-ins you already have; there is no hosted service and no stored secret.

![Software Giga Factory: a staggered schedule activates each project’s software factory. Prompts drive dependency updates, refactoring, simplification, and more; each runs in an isolated worktree, opens a pull request, and passes through project checks and maintainer review, with findings returned for fixes. Weekly group schedules, monthly prompts when due, one repository and due prompt at a time.](https://raw.githubusercontent.com/IndrajeetPatil/llm-dependabot/main/docs/images/giga-factory.webp)

![How llm-dependabot works: scheduled jobs start the app and login environment, repositories are prepared in isolated Git worktrees, and the coding agent opens pull requests for later cleanup.](https://raw.githubusercontent.com/IndrajeetPatil/llm-dependabot/main/docs/images/architecture-overview.webp)

I use it to maintain my own open-source repositories: web applications,
Python and R packages, and everything else. They receive dependency updates
every week (every month for R packages), and once a month a pass that
simplifies the code with what the updated dependencies now offer.

## Build your own

llm-dependabot is meant to be forked and configured to suit you:

- **Your repositories:** set the GitHub account, the prompts and how often
  they run, and the groups and their weekdays in `config.yaml`.

- **Your coding agent:** any agent with a non-interactive mode works, such
  as Antigravity CLI (the one configured here), Claude Code, Codex CLI, or
  GitHub Copilot CLI.

- **Your operating system:** the scheduling and tooling are macOS's
  (`launchd` and Homebrew); on another system, swap in its scheduler and
  package manager.

> [!IMPORTANT]
> The repositories you maintain must carry what the agent needs: a committed
> prompt for each kind of maintenance, guidance such as an `AGENTS.md`, and
> checks (tests, linters, and CI) that it can run to verify its changes.

See [Forking and adapting](https://www.indrapatil.com/llm-dependabot/configuration/#forking-and-adapting)
for what to change.

## Quick start

> [!NOTE]
> As configured here, llm-dependabot runs on macOS.

```sh
gh repo fork IndrajeetPatil/llm-dependabot --clone
cd llm-dependabot
make setup
```

`make setup` interactively installs what is missing, signs you in to GitHub
and your coding agent, sets the account whose repositories it maintains, asks
which private repositories to include, and loads the schedule. See
[Setup](https://www.indrapatil.com/llm-dependabot/setup/) for the details.

## Documentation

The full documentation is at <https://www.indrapatil.com/llm-dependabot/>.

| Guide | Covers |
| --- | --- |
| [Setup](https://www.indrapatil.com/llm-dependabot/setup/) | Requirements, `make setup`, Full Disk Access, and uninstalling |
| [Configuration](https://www.indrapatil.com/llm-dependabot/configuration/) | The coding agent, prompts and their cadences, the schedule, and adapting a fork |
| [Usage](https://www.indrapatil.com/llm-dependabot/usage/) | Everyday commands, logs, files on disk, and troubleshooting |
| [Architecture](https://www.indrapatil.com/llm-dependabot/architecture/) | How a run works and why it is built this way |
| [Development](https://www.indrapatil.com/llm-dependabot/development/) | Toolchain, checks, CI, and the documentation site |
| [LLMs](https://www.indrapatil.com/llm-dependabot/integrations/llms/) | The documentation in the `llms.txt` format |

## License

[MIT](https://github.com/IndrajeetPatil/llm-dependabot/blob/main/LICENSE)
