# Development

## Toolchain

![Development toolchain and tech stack: three bands covering runtime and inline dependencies with uv and Python 3.15, core libraries and the native Full Disk Access launcher, and local hygiene checks with Ruff, ty, prek git hooks, and uv audit.](images/tech-stack.webp)

- **Python 3.15** in a single-file [uv](https://docs.astral.sh/uv/) script
  with inline dependencies, locked in `llm_dependabot.py.lock`; there is no
  virtual environment to manage.

- **[Ruff](https://docs.astral.sh/ruff/)** lints (with every rule enabled)
  and formats.

- **[ty](https://docs.astral.sh/ty/)** type-checks against the script's own
  environment.

- **[prek](https://prek.j178.dev)** runs the git hooks.

- **`uv audit`** checks the locked dependencies of both scripts and the docs
  project against the OSV vulnerability database.

- **[Zensical](https://zensical.org)** builds this documentation into a
  website. It is the only dependency of the docs-only uv project in
  `pyproject.toml`, locked in `uv.lock`.

- **[Homebrew](https://brew.sh)** installs the command-line tools listed in
  the [`Brewfile`](https://github.com/IndrajeetPatil/llm-dependabot/blob/main/Brewfile).

Every check runs locally, and the GitHub Actions workflows in
[`.github/workflows/`](https://github.com/IndrajeetPatil/llm-dependabot/tree/main/.github/workflows)
run them again on each pull request:

| Workflow | Runs | Trigger |
| --- | --- | --- |
| `qa.yml` | `make check` | Pull requests |
| `prek.yml` | The prek hooks other than Ruff and ty | Pull requests |
| `security.yml` | Gitleaks over the full history and zizmor over the workflows | Pull requests |
| `conventional-commits.yml` | Commit messages and the pull-request title | Pull requests |
| `link-check.yml` | lychee over every link | Pull requests |
| `docs.yml` | Builds the site; deploys it to GitHub Pages from `main` | Pull requests, `main`, and by hand |

## Checks

```sh
make hooks-install   # once per clone: install the git hooks
make check           # ruff check, ruff format --check, ty check, and audit
make audit           # check locked dependencies for known vulnerabilities
make format          # apply ruff formatting
make hooks           # run every prek hook on all files
make update-deps     # upgrade locked dependencies and prek hook revisions
make docs            # build the documentation site, failing on any warning
make docs-serve      # preview the documentation site locally
```

The hooks in [`prek.toml`](https://github.com/IndrajeetPatil/llm-dependabot/blob/main/prek.toml) run Ruff and ty, tidy whitespace, verify VCS
permalinks and hook applicability, block direct commits to `main`, and
guard against case conflicts, illegal Windows filenames, destroyed
symlinks, private keys, large files, and merge-conflict markers. A local
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
