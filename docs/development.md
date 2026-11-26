# Development

## Package layout

The modules below live in `src/llm_dependabot/`. Each module may import
from those above it. `cli.py` handles argument parsing and delegates to
the other modules.

| Module | Responsibility |
| --- | --- |
| `paths.py` | Names and locations: the checkout, logs, state, launchd, and the app |
| `shell.py` | Logging, failing, and running external commands |
| `config.py` | `config.yaml` and `private.yaml` models, validation, and loading |
| `github.py` | Repository and pull request models, and every `gh` call |
| `state.py` | Pending pull requests, recovery checkouts, managed clones, and last runs in `state.json` |
| `discovery.py` | Sorting owned repositories that carry prompts into groups |
| `checkouts.py` | Worktrees for runs, and cleanup once pull requests finish |
| `runner.py` | Planning due prompts, running the agent, and the run lock |
| `launchd.py` | The launchd agents and `launchctl` |
| `macos_app.py` | Building the LLM Dependabot app and checking Full Disk Access |
| `install.py` | Installing the app and the agents together |
| `setup_wizard.py` | The steps of the interactive `setup` |
| `dashboard/` | Reading runs back from the logs (`runs.py`) and rendering them (`render.py`) |
| `cli.py` | The Typer commands, which parse arguments and call the modules above |

## Toolchain

![Development toolchain and tech stack: four bands cover the Python package and locked project dependencies, core libraries and the native Full Disk Access launcher, local Ruff, ty, pyrefly, unref, uv audit, deptry, and prek checks, and pull-request CI and supply-chain checks with GitHub Actions, actionlint, zizmor, Gitleaks, actions.lock, Zensical, Homebrew, and the Brewfile.](images/tech-stack.webp)

- **Python 3.14 or later** (3.15 in `.python-version`, which development
  and scheduled runs use) in a [uv](https://docs.astral.sh/uv/) project: the
  `llm_dependabot` package under `src/`, with its dependencies locked in
  `uv.lock`. uv creates and syncs the virtual environment on each run, and
  `make build` builds the sdist and wheel with the `uv_build` backend.

- **The `dev` dependency group** in `pyproject.toml` holds the development
  tools, locked in `uv.lock` like everything else, so new rules arrive only
  through a reviewed dependency update. Scheduled runs pass `--no-dev` and
  never install them.

- **[Ruff](https://docs.astral.sh/ruff/)** lints (with every rule, including
  preview rules and Google-style docstring checks, enabled) and formats.

- **[pytest](https://docs.pytest.org)** runs the test suite in `tests/`. It
  puts fake `gh`, `launchctl`, and other external commands first on `PATH`,
  runs real `git` against local repositories, and redirects every per-user
  path to a temporary directory, so it runs on any OS. It runs in strict mode,
  in random order ([pytest-random-order](https://github.com/jbasko/pytest-random-order)),
  and turns every warning into an error, and
  **[coverage.py](https://coverage.readthedocs.io)** requires 100% line and
  branch coverage.

- **[ty](https://docs.astral.sh/ty/)** type-checks against the project's own
  environment, and **[pyrefly](https://pyrefly.org)** requires complete
  strict type coverage.

- **[unref](https://github.com/Apakottur/unref)** finds unused code, and
  **[deptry](https://deptry.com)** checks that `pyproject.toml` declares
  exactly the dependencies the package imports.

- **[prek](https://prek.j178.dev)** runs the git hooks.

- **[actionlint](https://github.com/rhysd/actionlint)**,
  **[zizmor](https://docs.zizmor.sh)**, and
  **[Gitleaks](https://github.com/gitleaks/gitleaks)** lint and audit the
  workflows and scan for secrets, and the
  [`gh-actions-lock`](https://github.com/github/gh-actions-lock) extension
  maintains the workflow dependency lockfile.

- **`uv audit`** checks the locked dependencies of the project and of the
  private-names hook script against the OSV vulnerability database.

- **[Zensical](https://zensical.org)** builds this documentation into a
  website. It is the only package in the `docs` dependency group of
  `pyproject.toml`, so scheduled runs never install it.

- **[Homebrew](https://brew.sh)** installs the command-line tools listed in
  the [`Brewfile`](https://github.com/IndrajeetPatil/llm-dependabot/blob/main/Brewfile).

Every check runs locally, and the GitHub Actions workflows in
[`.github/workflows/`](https://github.com/IndrajeetPatil/llm-dependabot/tree/main/.github/workflows)
run them again on each pull request. `astral-sh/setup-uv` installs uv and
caches dependencies between runs, keyed on `pyproject.toml`, `uv.lock`, and
the hook script's lockfile. uv downloads managed Python interpreters on demand;
they are not cached between runs:

| Workflow | Runs | Trigger |
| --- | --- | --- |
| `qa.yml` | `make check`, and `make test` on the minimum Python in `requires-python` | Pull requests |
| `prek.yml` | The prek hooks other than Ruff and ty | Pull requests |
| `security.yml` | Gitleaks over the full history and zizmor over the workflows | Pull requests |
| `conventional-commits.yml` | Commit messages and the pull-request title | Pull requests |
| `link-check.yml` | lychee over every link | Pull requests |
| `docs.yml` | Builds the site; deploys it to GitHub Pages from `main` | Pull requests, `main`, and by hand |

### Workflow security

Keep these rules when changing the workflows. Repositories created from
this template inherit them.

- Run checks on pull requests to `main`. Only `docs.yml` also runs on
  `main` and by hand for deployment. Keep workflows self-contained so
  template users can run them with their own repository settings. Avoid
  reusable workflow calls in the template.

- Every action is pinned to a full commit SHA with its release in an inline
  comment (for example, `# v7.0.1`), and [`.github/zizmor.yml`](https://github.com/IndrajeetPatil/llm-dependabot/blob/main/.github/zizmor.yml)
  makes zizmor reject any other pin.

- `actions.lock` in
  [`.github/workflows/`](https://github.com/IndrajeetPatil/llm-dependabot/tree/main/.github/workflows)
  is a machine-generated
  [workflow dependency lockfile](https://docs.github.com/en/actions/concepts/security/workflow-dependency-lockfiles)
  (in public preview). It records every direct and transitive action with its
  commit and source repository identity. Run `make actions-lock` after
  changing a `uses:` line; the `actions-lock-verify` hook fails a commit
  whose lockfile is stale.

- Set `GITHUB_TOKEN` to `contents: read` at workflow level. Grant additional
  permissions only to the job that needs them and document why. Set
  `persist-credentials: false` on every checkout.

- Give each job a finite `timeout-minutes` and each workflow a
  `concurrency` group. Pass event data and inputs to scripts through
  `env:` instead of interpolating expressions into `run:`.

- Prefer runner-provided tools. For standalone binaries such as Gitleaks,
  pin the version and archive SHA-256, verify the checksum before
  extraction, and update both pins together.

- Keep Gitleaks scanning the full history in CI and the staged diff on
  commit. Audit every workflow with zizmor in pedantic mode. Keep both
  checks fail-closed and fix findings at their source.

- Use `astral-sh/setup-uv` to install uv, select the required Python
  version, and cache dependencies. Let uv download managed interpreters
  on demand. Keep Python and dependency setup in uv. Keep tools with
  dedicated actions or prek hooks on those integrations.

- Keep zizmor's version, conventional-pre-commit's version, and the
  allowed commit types in sync between the workflows and `prek.toml`.
  Update the workflow table and permitted action list here when they change.

If your account allows only selected actions, allow these:

- `actions/checkout`, `actions/upload-pages-artifact`, and
  `actions/deploy-pages` (and the `actions/upload-artifact` they use)
- `astral-sh/setup-uv`
- `j178/prek-action`
- `lycheeverse/lychee-action`
- `zizmorcore/zizmor-action` (and the `github/codeql-action` it uses)

## Checks

```sh
make hooks-install   # once per clone: install the git hooks
make check           # lint, format check, type check and coverage, tests, dead code, audit, and build
make test            # run the pytest suite and require full coverage
make audit           # check dependencies for known vulnerabilities and declarations
make build           # build the sdist and wheel into dist/
make format          # apply ruff formatting
make hooks           # run every prek hook on all files
make update-deps     # upgrade locked dependencies and prek hook revisions
make actions-lock    # regenerate the workflow dependency lockfile
make actions-lock-verify  # check the lockfile against the workflows
make docs            # build the documentation site, failing on any warning
make docs-serve      # preview the documentation site locally
```

The hooks in [`prek.toml`](https://github.com/IndrajeetPatil/llm-dependabot/blob/main/prek.toml) run Ruff and ty, lint the workflows
with actionlint and audit them with zizmor, verify the workflow lockfile,
scan staged changes with Gitleaks, check commit messages against
Conventional Commits, tidy whitespace, verify VCS permalinks and hook
applicability, block direct commits to `main` and submodules, and guard
against case conflicts, illegal Windows filenames, destroyed symlinks,
private keys, large files, and merge-conflict markers. CI skips the hooks
that another workflow already runs or that need local tools. A local
hook,
[`hooks/check_private_names.py`](https://github.com/IndrajeetPatil/llm-dependabot/blob/main/hooks/check_private_names.py), fails any
commit whose files or message name a repository listed in `private.yaml`, or
that adds `private.yaml` itself.

## Documentation site

The pages in `docs/` are a [Zensical](https://zensical.org) site configured
in [`mkdocs.yml`](https://github.com/IndrajeetPatil/llm-dependabot/blob/main/mkdocs.yml)
and published at <https://www.indrapatil.com/llm-dependabot/>. It uses the
same theme and set-up as the owner's other documentation sites, and also
publishes `llms.txt`, `llms-full.txt`, a Markdown copy of every page, and a
`robots.txt` that welcomes AI crawlers. To keep it building:

- The home page, `docs/index.md`, only includes `README.md`, so the README
  and the site's landing page are the same text. Give its images and links
  absolute URLs, so they work on GitHub and on the site alike.

- Add a new page to `nav`, and to the `llmstxt` sections, in `mkdocs.yml`.

- Link to other pages and images with paths relative to `docs/`; link to
  anything outside `docs/` with its full GitHub URL, since the site only
  contains `docs/`.

- Link to a new documentation page from the README after it is deployed.
  Use code formatting for paths to new files outside `docs/` until their
  GitHub URLs resolve on `main`. The link check fetches absolute URLs
  from the live site and GitHub.

- Use GitHub callouts (`> [!NOTE]`, `> [!TIP]`, `> [!IMPORTANT]`, and
  `> [!WARNING]`) for asides: GitHub renders them as alerts and the site as
  admonitions.

- [`overrides/`](https://github.com/IndrajeetPatil/llm-dependabot/tree/main/overrides)
  adds structured data and `llms.txt` links to every page, and points the home
  page's edit and view buttons at `README.md`.

## Maintaining llm-dependabot itself

This repository commits its own prompts, so llm-dependabot maintains itself
like any other participating repository:

- [`update-deps`](https://github.com/IndrajeetPatil/llm-dependabot/blob/main/.github/prompts/update-deps.md)
  upgrades the locked dependencies and prek hooks.

- [`simplify-codebase`](https://github.com/IndrajeetPatil/llm-dependabot/blob/main/.github/prompts/simplify-codebase.md)
  removes custom code that a newer dependency feature or a proven library
  makes unnecessary.

Its pull requests change the tool that is running them. Each run works in its
own worktree, so the checkout the scheduled jobs run from is untouched until
`make self-update` pulls the merged change into it (see
[Setup](setup.md#update-llm-dependabot)).

## Releases

A release is a Git tag and a GitHub release whose notes match the
[changelog](changelog.md); llm-dependabot runs from its checkout, so it is not
published to PyPI. The owner runs the `create-release` prompt in
`.github/prompts/` by hand: it bumps the version with `uv version`, dates the
changelog's `Unreleased` section, merges that as a release pull request, and
tags the merge commit with `gh release create`.

## Design

[`DESIGN.md`](https://github.com/IndrajeetPatil/llm-dependabot/blob/main/DESIGN.md) records the visual identity, shared with
indrapatil.com. Generated documentation figures follow the
[documentation-illustrations skill](https://github.com/IndrajeetPatil/llm-dependabot/blob/main/.agents/skills/documentation-illustrations/SKILL.md),
with their prompts recorded in [images/README.md](https://github.com/IndrajeetPatil/llm-dependabot/blob/main/docs/images/README.md).

## Hex sticker and app icon

[`hextools/`](https://github.com/IndrajeetPatil/llm-dependabot/tree/main/hextools) holds the sticker artwork and the R scripts that
render `docs/images/logo.png`, the LLM Dependabot app icon, `app/icon.png`,
and the social preview card, `docs/images/social-card.png`. See
[its README](https://github.com/IndrajeetPatil/llm-dependabot/blob/main/hextools/README.md).
