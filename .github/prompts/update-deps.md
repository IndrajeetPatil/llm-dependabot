---
name: update-deps
description: Update dependencies and ensure the codebase is compatible with the latest versions
---

# Update Dependencies and Refactor Codebase

Run `make update-deps` to upgrade the locked dependencies of `llm_dependabot.py`
(`llm_dependabot.py.lock`) and the `prek` hook revisions. Then iterate until the
full local quality gate passes:

- `make check` (including `uv audit` of the locked dependencies)
- `make hooks`
- `make dry-run GROUP=python` (a smoke test that loads the configuration and
  queries GitHub without running the agent)

Fix any breaking API changes, type errors, lockfile drift, or lint failures
introduced by the upgrades.

Ensure that the minimum versions in the inline `# /// script` metadata of
`llm_dependabot.py` match the newly locked versions, and that the dependencies
there remain alphabetically sorted. Keep the PyYAML minimum in
`hooks/check_private_names.py` equal to the one in `llm_dependabot.py`. After
editing the metadata, run `uv lock --script llm_dependabot.py` so the lockfile
matches it.

`make update-deps` runs `prek update --freeze`, which refreshes each prek hook
to its latest tag but records the resolved commit SHA in `rev` with a
`# frozen: <tag>` comment. Never rewrite a frozen `rev` back to a bare mutable
tag.

If the `requires-python` floor is no longer the latest stable CPython, raise it
in both scripts and in `ruff.toml` and `ty.toml`, and adopt the new version's
features where they simplify the code.

Do not change anything under `app/`: rebuilding the LLM Dependabot app
invalidates its Full Disk Access grant. Do not run `make setup`,
`make install`, `make run`, or `make cleanup`.

Once the dependency update is green, review relevant changelogs and current
documentation for upgraded libraries. Apply small compatibility
simplifications only when they reduce local complexity or remove a workaround,
and rerun the affected checks after each change. Update `docs/` if behaviour
or commands change.

Open a ready-for-review (not draft) PR with `gh pr create`. In the PR body,
summarise dependency groups changed, compatibility fixes made, validation
commands that passed, and any key refactorings as list items.
