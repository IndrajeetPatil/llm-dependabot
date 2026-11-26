# AGENTS.md

llm-dependabot runs repositories' committed prompts with a configurable coding
agent on a macOS `launchd` schedule. See the [architecture](docs/architecture.md)
for the runtime design.

## The live checkout

The owner's checkout runs the scheduled jobs. Keep it on `main` and clean.
Create a separate worktree from `origin/main` for changes and remove it after
the PR merges.

- Run `make setup`, `make install`, `make self-update`, `make uninstall`,
  `make run`, or `make cleanup` only when explicitly asked. These commands
  change the live installation, execute agents with automatic approvals, or
  delete checkouts. Use `make dry-run GROUP=python` to inspect the run plan.

- Use the owner's `make self-update` workflow to bring merged changes into
  the live checkout. For changes to `app/`, `Brewfile`, uv's
  `required-version`, `config.yaml`, `launchd.py`, or `macos_app.py`, state
  the relevant [update steps](docs/setup.md#update-llm-dependabot) in the PR.
  An app rebuild requires a fresh Full Disk Access grant.

- Keep private repository names in the ignored `private.yaml`. Exclude
  them from commits, files staged for commit, and PR text.

## Working on the code

- Keep `cli.py` to argument parsing and respect the dependency order in the
  [module map](docs/development.md#package-layout). Keep owner, bundle ID,
  clone root, schedule, and agent settings in `config.yaml`. Keep the code
  and docs agent-neutral, identifying Antigravity CLI as the default when
  relevant. Load dashboard assets from separate files with
  `importlib.resources`.

- Preserve and track agent work when its outcome is uncertain. Count only
  successful exits towards cadence. Exercise processes that ignore graceful
  termination in timeout tests and preserve recovery work in cleanup tests.

- Prefer the Makefile targets. Run `make check` and `make hooks` before
  committing, and `make docs` for documentation changes. Use `make help` to
  discover targets and `uv run pytest -k NAME` for focused test runs.

- Test every behaviour change and maintain 100% line and branch coverage.
  Isolate tests from the real home directory and `config.yaml`. Use the
  `commands` fixture for external commands and real Git on local bare
  repositories. Keep tests portable across Linux and macOS. Parametrise cases
  of a single behaviour with explicit IDs and fix warning or order-dependent
  failures at their source.

- Use uv-managed Python and locked dependencies. Put development tools in
  the `dev` group and lock standalone scripts with inline dependencies.
  Target the `requires-python` floor and pass `encoding="utf-8"` to text-mode
  file and subprocess calls.

- Annotate code throughout and defer to ty if it disagrees with pyrefly.
  Write Google-style docstrings with a summary and any rationale the
  signature cannot convey. Omit `Args:`, `Returns:`, `Yields:`, and
  `Raises:` sections. Fix Ruff findings at their source and justify any
  necessary ignore using the rule name. Document new configuration ignores
  in `pyproject.toml`.

## Task-specific guidance

| When | Read |
| --- | --- |
| Changing workflows | [Workflow security and maintenance](docs/development.md#workflow-security) |
| Changing documentation | [Documentation site conventions](docs/development.md#documentation-site) |
| Changing visuals | [Design guidelines](DESIGN.md) |
| Generating documentation figures | [Documentation illustrations skill](.agents/skills/documentation-illustrations/SKILL.md) |
| Preparing a release | [Create-release prompt](.github/prompts/create-release.md) |

Use British English. Keep the README to an overview, quick start, and links.
Update the relevant guide when behaviour, commands, configuration, or
external files change. Keep user-facing entries in `CHANGELOG.md` under
`Unreleased`, including before the first release. The site includes that
file through `docs/changelog.md`.

When incorrect guidance contributes to a mistake, fix it alongside the code
and keep the quality gates intact.

## Pull requests

- Use Conventional Commits (`type(scope): description`) for commits and PR
  titles. Use lowercase imperative descriptions and the types in
  `conventional-commits.yml`. Open ready PRs with `gh pr create`, keep their
  metadata current, and omit agent attribution.

- Require green hosted CI and, where automatic Codex review is enabled,
  approval of the current head with no unresolved findings. Fix failures,
  reply to addressed findings, and resolve their threads.
  Mention the review bot only with the trigger `@codex review`, once after
  explicitly exhausted review usage refreshes. Leave the PR open if usage
  is exhausted.

- Recheck the head, checks, and review threads before squash-merging, then
  verify the merge. Respect branch protections. Update from `main` only for
  conflicts or dependencies.
  Report local validation, hosted CI, review, and merge state separately.
