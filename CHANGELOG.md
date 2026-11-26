# Changelog

All notable changes to llm-dependabot are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

The first stable release.

### Added

- Run the prompts that repositories commit, such as `update-deps`,
  `simplify-codebase`, and `gsc-analysis`, with a coding agent on a weekly or
  monthly cadence, through `launchd` on macOS.

- Discover every public repository that carries a configured prompt, include
  private ones listed in `private.yaml`, and sort them into groups by primary
  language, each with its own weekday, time, and per-prompt cadence.

- Run any agent that has a non-interactive mode, configured in
  `config.yaml`, with Antigravity CLI as the default.

- Work in a fresh worktree for each run, label the pull requests it opens,
  and clean up worktrees and run-only clones once those pull requests are
  merged or closed.

- Set up interactively with `make setup`: Homebrew packages, sign-ins,
  private repositories, Git hooks, the `launchd` agents, and Full Disk Access
  for the LLM Dependabot app, whose bundle identifier `config.yaml` sets.

- Review past runs, their pull requests, and agent transcripts in an HTML
  dashboard (`make dashboard`), and the schedule in `make status`.

- Support Python 3.14 and later; the checkout runs on the newest stable
  release, named in `.python-version`.

- Pull merged changes into the checkout the scheduled jobs run from with
  `make self-update`; `make status` and every run warn when that checkout is
  behind `origin/main` or has another branch checked out.

### Fixed

- Retain failed and interrupted agent work for manual recovery, including when
  the final pull request lookup fails; show recovery paths in `make status`
  and protect their managed clones from cleanup.

- Keep failed and timed-out agents eligible for the next monthly run, while
  continuing to track any pull request they opened.

- Force remaining agent processes to stop after a bounded graceful shutdown
  when a run times out.
