# AGENTS.md

Guidance for AI coding agents working in this repository.

## Overview

`llm-dependabot` runs each of the owner's repositories' `update-deps`
prompt with Antigravity CLI (`agy`) on a weekly `launchd` schedule (macOS only).
See [README.md](README.md) for behaviour and setup.

## Layout

| Path | Purpose |
| --- | --- |
| `update_deps.py` | The whole CLI: a single-file `uv` script (Python 3.15+, PyYAML only) |
| `config.yaml` | Shared settings and the source of truth for groups, weekdays, and times |
| `private.example.yaml` | Template for the git-ignored `private.yaml` listing private repositories |
| `launcher.c` | Small launcher that holds the macOS Full Disk Access grant |
| `ruff.toml`, `ty.toml` | Lint, format, and type-check configuration |
| `Makefile` | Entry points for common operations (`make help`) |

## Commands

Prefer the Makefile targets over invoking tools directly:

```sh
make help          # list all targets
make check         # lint, format check, and type check (run before committing)
make format        # apply ruff formatting
make list          # show group assignment (needs gh authenticated)
make dry-run GROUP=python
```

`make install`, `make uninstall`, `make run`, and `make cleanup` change the
user's `launchd` agents, run the agent in YOLO mode, or delete checkouts. Do
not run them unless explicitly asked; they only work on the owner's Mac.

## Conventions

- Keep the CLI a single script; PyYAML is its only dependency, so prefer the
  standard library for anything else.
- Ruff runs with `select = ["ALL"]`; fix findings rather than adding ignores,
  and justify any new ignore in a comment in `ruff.toml`.
- Add type annotations everywhere; `ty check` must pass.
- Update `README.md` when behaviour, commands, or files outside the repository
  change, and keep the module docstring in `update_deps.py` in sync with the
  subcommands.
- Do not hard-code the owner, clone root, or schedule in code; they belong in
  `config.yaml`.
- Never name a private repository in any committed file, commit message, or
  pull request; private repositories are listed only in `private.yaml`.
- Use British English in prose.
