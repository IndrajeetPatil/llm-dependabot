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
| `llm_dependabot.py` | The whole CLI: a single-file `uv` script (Python 3.15+) |
| `llm_dependabot.py.lock` | Locked versions of the script's dependencies |
| `config.yaml` | Shared settings and the source of truth for prompts, cadences, groups, weekdays, and times |
| `private.example.yaml` | Template for the git-ignored `private.yaml` listing private repositories |
| `app/` | Sources of the LLM Dependabot app (`launcher.c`, `icon.png`), which holds the Full Disk Access grant |
| `docs/` | User and developer documentation, built into a Zensical site; `docs/images/logo.png` is the hex sticker |
| `zensical.toml` | Documentation site configuration and navigation |
| `pyproject.toml`, `uv.lock` | Docs-only uv project that installs Zensical |
| `.github/workflows/` | CI workflows: checks on pull requests, docs deployment from `main` |
| `DESIGN.md` | Visual identity for the sticker, app icon, and documentation figures |
| `.agents/skills/documentation-illustrations/` | Skill for generating documentation figures |
| `.github/prompts/update-deps.md` | This repository's own dependency-update prompt |
| `hextools/` | Artwork and R scripts that render the hex sticker, `app/icon.png`, and the social preview card |
| `hooks/check_private_names.py` | Hook that keeps private repository names out of commits |
| `prek.toml` | Git hooks, run with `make hooks` |
| `ruff.toml`, `ty.toml` | Lint, format, and type-check configuration |
| `Makefile` | Entry points for common operations (`make help`) |
| `Brewfile` | Command-line tools that `make setup` installs with `brew bundle` |

## Commands

Prefer the Makefile targets over invoking tools directly:

```sh
make help          # list all targets
make check         # lint, format check, type check, and dependency audit
make hooks         # every prek hook on all files; must pass before committing
make format        # apply ruff formatting
make update-deps   # upgrade locked dependencies and prek hooks
make list          # show group assignment (needs gh authenticated)
make dry-run GROUP=python
make docs          # build the documentation site strictly
```

`make setup`, `make install`, `make uninstall`, `make run`, and `make cleanup`
change the user's `launchd` agents, run the agent in YOLO mode, or delete
checkouts. Do not run them unless explicitly asked; they only work on the
owner's Mac.

## Conventions

- Keep the CLI a single uv script with inline dependencies. Prefer widely used,
  maintained libraries (Rust-backed where available) over hand-written code;
  the current ones are Typer, pydantic, PyYAML, and filelock.

- Ruff runs with `select = ["ALL"]`; fix findings rather than adding ignores,
  and justify any new ignore in a comment in `ruff.toml`.

- Add type annotations everywhere; `ty check` must pass.

- Keep the documentation site building with `make docs`: register new pages
  in `zensical.toml`, and link outside `docs/` with full GitHub URLs.

- Keep the README short: an overview, the quick start, and links. Put details
  in the matching page under `docs/`, and update it when behaviour, commands,
  configuration, or files outside the repository change.

- Follow `DESIGN.md` for anything visual: the hex sticker, the app icon,
  diagrams, and illustrations.

- Changing anything under `app/` rebuilds the app and invalidates its Full
  Disk Access grant, so the user must grant it again; avoid needless changes.

- Do not hard-code the owner, clone root, schedule, or agent in code; they
  belong in `config.yaml`. Keep code and docs agent-neutral, naming
  Antigravity CLI only as the default.

- Never name a private repository in any committed file, commit message, or
  pull request; private repositories are listed only in `private.yaml`.

- Use British English in prose.
