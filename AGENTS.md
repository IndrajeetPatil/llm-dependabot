# AGENTS.md

Guidance for AI coding agents working in this repository.

## Overview

`llm-dependabot` runs the owner's repositories' committed prompts (such as
`update-deps` and `simplify-codebase`) with a configurable coding agent
(Antigravity CLI, `agy`, by default) on a weekly or monthly `launchd` schedule
(macOS only). See
[README.md](README.md) for an overview and [docs/](docs) for details, notably
[docs/architecture.md](docs/architecture.md).

## Layout

| Path | Purpose |
| --- | --- |
| `src/llm_dependabot/` | The CLI package (Python 3.14+, run on the 3.15 in `.python-version`); see the module map below |
| `src/llm_dependabot/dashboard/templates/` | The dashboard's HTML, CSS, and JavaScript |
| `tests/` | pytest suite, one file per module; `conftest.py` redirects every per-user path to a temporary directory and provides the `commands` fixture of fake executables |
| `config.yaml` | Shared settings and the source of truth for prompts, cadences, groups, weekdays, and times |
| `private.example.yaml` | Template for the git-ignored `private.yaml` listing private repositories |
| `app/` | Sources of the LLM Dependabot app (`launcher.c`, `icon.png`), which holds the Full Disk Access grant |
| `docs/` | User and developer documentation, built into a Zensical site; `docs/images/logo.png` is the hex sticker |
| `mkdocs.yml` | Documentation site configuration, navigation, and `llms.txt` sections |
| `lychee.toml` | Link-check settings for the CI link check |
| `overrides/` | Site template overrides: structured data, `llms.txt` links, and README edit links |
| `pyproject.toml`, `uv.lock` | The uv project: package metadata, CLI dependencies and entry point, the `dev` group of development tools, the `docs` group with Zensical, and tool configuration |
| `.github/workflows/` | CI workflows: checks on pull requests, docs deployment from `main` |
| `.github/workflows/actions.lock` | Generated lockfile of every workflow's direct and transitive actions |
| `.github/zizmor.yml` | zizmor policy that requires full-SHA action pins |
| `DESIGN.md` | Visual identity for the sticker, app icon, and documentation figures |
| `.agents/skills/documentation-illustrations/` | Skill for generating documentation figures |
| `.github/prompts/` | This repository's own `update-deps` and `simplify-codebase` prompts, which run on the schedule, and `create-release`, which the owner runs by hand |
| `CHANGELOG.md` | Release notes, also the documentation's changelog page (`docs/changelog.md` only includes it) |
| `hextools/` | Artwork and R scripts that render the hex sticker, `app/icon.png`, and the social preview card |
| `hooks/check_private_names.py` | Hook that keeps private repository names out of commits |
| `prek.toml` | Git hooks, run with `make hooks` |
| `Makefile` | Entry points for common operations (`make help`) |
| `Brewfile` | Command-line tools that `make setup` installs with `brew bundle` |

### Modules

Each module depends only on those above it; `cli.py` holds no logic of its own.

| Module | Responsibility |
| --- | --- |
| `paths.py` | Names and locations: the checkout, logs, state, launchd, and the app |
| `shell.py` | Logging, failing, and running external commands |
| `config.py` | `config.yaml` and `private.yaml` models, validation, and loading |
| `github.py` | Repository and pull request models, and every `gh` call |
| `state.py` | Pending pull requests, managed clones, and last runs in `state.json` |
| `discovery.py` | Sorting owned repositories that carry prompts into groups |
| `checkouts.py` | Worktrees for runs, and cleanup once pull requests finish |
| `runner.py` | Planning due prompts, running the agent, and the run lock |
| `launchd.py` | The launchd agents and `launchctl` |
| `macos_app.py` | Building the LLM Dependabot app and checking Full Disk Access |
| `install.py` | Installing the app and the agents together |
| `setup_wizard.py` | The steps of the interactive `setup` |
| `dashboard/` | Reading runs back from the logs (`runs.py`) and rendering them (`render.py`) |
| `cli.py` | The Typer commands, which parse arguments and call the modules above |

## Commands

Prefer the Makefile targets over invoking tools directly:

```sh
make help          # list all targets
make check         # lint, format check, type check and coverage, tests, dead code, audit, and build
make test          # the pytest suite with 100% line and branch coverage (uv run pytest -k NAME for one test)
make build         # build the sdist and wheel into dist/
make hooks         # every prek hook on all files; must pass before committing
make format        # add missing trailing commas, then apply ruff formatting
make update-deps   # upgrade locked dependencies and prek hooks
make actions-lock  # regenerate .github/workflows/actions.lock after action changes
make list          # show group assignment (needs gh authenticated)
uv run llm-dependabot --help  # the CLI that the everyday targets wrap
make dry-run GROUP=python
make docs          # build the documentation site strictly
```

`make setup`, `make install`, `make self-update`, `make uninstall`, `make run`,
and `make cleanup` change the user's `launchd` agents, run the agent in YOLO mode, or delete
checkouts. Do not run them unless explicitly asked; they only work on the
owner's Mac.

## The live checkout

The owner's clone of this repository is also the running installation: the
launchd agents run the CLI from it (`uv run --project <checkout>`), so
whatever is checked out there is what the scheduled runs execute.

- Never switch the owner's main checkout to a feature branch or leave
  uncommitted work in it. Make changes in a separate worktree
  (`git worktree add ../llm-dependabot-<topic> -b <branch> origin/main`), and
  delete it with `git worktree remove` once the pull request is merged.

- Merged changes reach the installation only through `make self-update`.
  Python code and `uv.lock` changes need nothing more, since every run syncs
  from the lockfile; there is no package to rebuild or reinstall.

- When a pull request changes `app/`, the `Brewfile`, uv's
  `required-version`, or anything `make install` writes (`config.yaml`,
  `launchd.py`, `macos_app.py`), say in its body what the owner must do after
  merging: `make self-update`, granting Full Disk Access again, or
  `brew upgrade uv`.

## Conventions

- Keep the CLI a package under `src/llm_dependabot/` with its dependencies in
  `pyproject.toml`, locked in `uv.lock`. Put new code in the module that owns
  its concern (see the module map), keep `cli.py` to argument parsing, and
  never import from a module further down the map. Prefer widely used,
  maintained libraries (Rust-backed where available) over hand-written code;
  the current ones are Typer, pydantic, PyYAML, and filelock.

- Cover every change in behaviour with a test in the module's `tests/` file;
  `make test` requires 100% line and branch coverage. Tests run on Linux in
  CI: script `gh`, `launchctl`, and other external commands with the
  `commands` fixture, which puts fake executables first on `PATH`; use
  `monkeypatch` on the importing module for Python-level fakes; and use real
  `git` against a local bare repository instead of faking it. Never let a
  test touch the real home directory or `config.yaml`. Tests also run on the
  owner's Mac, so a fake must hold on both systems: replace platform-specific
  values such as `st_birthtime` rather than assume they are missing.

- pytest runs strictly (see `[tool.pytest]`): every warning is an error,
  tests run in random order, and markers, parametrisation ids, and config
  keys are checked. Fix a warning or an order dependence at its cause; never
  filter it out or pin the order. Parametrise cases of one behaviour, with
  `pytest.param(..., id=...)`, instead of copying a test.

- Keep non-Python assets, such as the dashboard's HTML, CSS, and JavaScript,
  in their own files, loaded with `importlib.resources`, not in Python strings.

- Ruff runs with `select = ["ALL"]` and preview rules; fix findings rather
  than adding ignores, and justify any new ignore in a comment in
  `pyproject.toml`. Name rules, not codes, in ignores and in
  `# ruff: ignore[rule-name] (reason)` comments.

- Give every module, class, and function a Google-style docstring: a summary
  line saying what it does, plus paragraphs on why when the behaviour is not
  obvious. Leave out `Args:`, `Returns:`, `Yields:`, and `Raises:` sections,
  which only restate the signature; Ruff's rules for them are ignored for
  that reason.

- Support every Python from the `requires-python` floor, one minor release
  below the latest, even though `.python-version` runs the latest: never use
  a language feature or API newer than the floor. ty checks against the
  floor, and CI runs the tests on it. Below Python 3.15, text I/O decodes
  with the locale's encoding, so pass `encoding="utf-8"` to every text-mode
  file and subprocess call (Ruff checks the files, not the subprocesses).

- Add type annotations everywhere; `ty check` and pyrefly's strict type
  coverage must pass. If they disagree, ty wins.

- Development tools belong in the `dev` dependency group, so `uv.lock` pins
  them; never run them with `uvx`. Scheduled runs use `--no-dev`.

- Keep the documentation site building with `make docs`: register new pages
  in `nav` and the `llmstxt` sections of `mkdocs.yml`, and link outside
  `docs/` with full GitHub URLs.

- The site's home page includes `README.md` verbatim, so give README images
  and links absolute URLs. The link check fetches those URLs from the live
  site, so link a new page from the README only in a follow-up pull request,
  once the site has deployed it. The same holds for GitHub URLs of files a
  pull request adds: they resolve only once it merges, so name new files in
  code formatting and link them in a follow-up.

- Use GitHub callouts (`> [!NOTE]`) for asides; the site renders them as
  admonitions.

- Keep the README short: an overview, the quick start, and links. Put details
  in the matching page under `docs/`, and update it when behaviour, commands,
  configuration, or files outside the repository change.

- Follow `DESIGN.md` for anything visual: the hex sticker, the app icon,
  diagrams, and illustrations.

- Changing anything under `app/` rebuilds the app and invalidates its Full
  Disk Access grant, so the user must grant it again; avoid needless changes.

- Do not hard-code the owner, bundle identifier, clone root, schedule, or
  agent in code; they belong in `config.yaml`. Keep code and docs
  agent-neutral, naming Antigravity CLI only as the default.

- Never name a private repository in any committed file, commit message, or
  pull request; private repositories are listed only in `private.yaml`.

## Workflows

Template users inherit these workflows, so keep them secure by default:

- Trigger checks on pull requests to `main` only; only `docs.yml` also runs
  on `main` and by hand, to deploy the site.

- Pin every action to a full commit SHA with its most specific release in an
  inline comment (`# v7.0.1`), never a sliding tag such as `v7`.

- Regenerate `.github/workflows/actions.lock` with `make actions-lock`
  whenever a `uses:` line changes; never edit it by hand. It records
  transitive actions and each source repository's identity, and the prek
  `actions-lock-verify` hook rejects drift.

- Default `GITHUB_TOKEN` to `contents: read` at the workflow level, and grant
  write scopes only to the job that needs them, with a comment saying why.

- Set `persist-credentials: false` on every checkout, a finite
  `timeout-minutes` on every job, and a `concurrency` group on every
  workflow.

- Pass event data and inputs to scripts through `env:`, never by
  interpolating `${{ }}` into `run:`.

- Prefer runner-provided tools over additional actions. Install a standalone
  binary only at a pinned version with a pinned SHA-256 checksum of the
  archive, verified before extraction, and update both together.

- Keep the security gate fail-closed: Gitleaks scans the complete history,
  and zizmor audits every workflow in pedantic mode. Fix findings rather than
  suppressing them.

- Keep tool versions that CI and prek share in step: zizmor in `security.yml`
  and `prek.toml`, and conventional-pre-commit and its commit types in
  `conventional-commits.yml` and `prek.toml`.

- Keep the workflow table and the list of actions in `docs/development.md`
  current when a workflow, or the set of actions it uses, changes: template
  users whose Actions policy allows only selected actions copy that list.

- Use British English in prose.

## Releases

A release is a Git tag and a GitHub release, never a PyPI upload: the CLI
runs from its checkout. To make one, follow
`.github/prompts/create-release.md`. Edit `CHANGELOG.md`, never
`docs/changelog.md`; the release collects every user-facing change since the
last one into its `Unreleased` section, so a pull request may add its entry
there but need not.

## Learn from mistakes

When a check fails, a reviewer raises a finding, or you notice a mistake in
your own work, fix it, then ask what led you to it. If `AGENTS.md`, a skill,
its scripts or templates, a prompt, or a doc gave missing, ambiguous, or
wrong guidance, correct that guidance in the same pull request, stating the
general rule rather than the incident. Never weaken a quality gate instead.

## Pull requests

Follow these rules without relying on any instructions outside this
repository:

- Write every commit message and PR title as a Conventional Commit,
  `type(scope): description`, lowercase and imperative, with a type from
  `conventional-commits.yml`; the `conventional-commits` check enforces it.

- Open every PR ready for review with `gh pr create`, never as a draft. Keep
  the title and body in step with the net diff.

- Never add agent or tool attribution to commits, PRs, or comments.

- After opening or pushing, wait for hosted CI to finish. Inspect failed jobs,
  fix the cause, run the local checks (`make check` and `make hooks`), push,
  and repeat. Skipped, queued, or failing required checks are not success.

- If an automatic AI review (Codex, for the owner) runs on the PR, wait for
  its result instead of requesting one. Fix merited findings, reply to and
  resolve addressed threads, and continue until the review approves the
  current head with no unresolved findings. Never write `@codex` anywhere in
  a PR, even in backticks: it cancels the automatic review. Say "a Codex
  review request" instead.

- If Codex reports exhausted usage, leave the PR open and report it; no other
  reviewer or silence counts as approval. Once usage refreshes, comment
  `@codex review` once; only this case needs the comment.

- Once CI is green and the review gate is met, squash-merge, then verify the
  merged state. Recheck the head, threads, and checks immediately before
  merging, and never bypass branch protections.

- Update a PR branch from `main` only to resolve conflicts or pick up a change
  the PR depends on, never just to bring it up to date.

- Report local validation, hosted CI, review, and merge state separately. If
  an external blocker stops completion, leave the PR open and say so.
