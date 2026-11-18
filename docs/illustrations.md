# Documentation illustrations

Prompts for generated figures in these docs, recorded so the next figure can
start from them. The rules are in [DESIGN.md](../DESIGN.md#documentation-illustrations),
and the [documentation-illustrations skill](../.agents/skills/documentation-illustrations/SKILL.md)
explains how to write a prompt.

The hex sticker is drawn by hand; see [hextools](../hextools/README.md).

## Catalogue

| Figure | Subject | Embedded in |
| --- | --- | --- |
| [`docs/images/architecture-overview.webp`](images/architecture-overview.webp) | Scheduled trigger, workspace isolation, and agent lifecycle | [README.md](../README.md) |
| [`docs/images/execution-lifecycle.webp`](images/execution-lifecycle.webp) | Permission boundary, repository isolation, and state locking | [docs/architecture.md](architecture.md) |
| [`docs/images/tech-stack.webp`](images/tech-stack.webp) | Runtime, dependencies, core libraries, and local QA checks | [docs/development.md](development.md) |
| [`docs/images/ecosystem-schedule.webp`](images/ecosystem-schedule.webp) | Staggered weekly schedule across ecosystem groups | [docs/configuration.md](configuration.md) |

## Prompts

### Architecture overview

- **File:** `docs/images/architecture-overview.webp`
- **Companion:** [`docs/images/architecture-overview.prompt.txt`](images/architecture-overview.prompt.txt)

```text
Use case: infographic-diagram. Asset type: documentation diagram for llm-dependabot, a macOS tool that runs an AI coding agent weekly to update dependencies. Landscape 3:2, flat canvas warm paper #faf8f4, ink #201d18, muted ink #5d574c, fine hairlines #e3ded2, deep teal #14584d accent for all step outline icons and connecting arrows, muted rust #9a3d2e only for failure stops. Fraunces-like serif title and band headings, Hanken-like sans labels, generous whitespace, flat outline icons in deep teal #14584d, thin orthogonal teal arrows. Match the reference style of flat warm-paper editorial documentation diagrams from indrapatil.com and python-package-quality-checks.webp. No shadows, gradients, texture, 3D, cards, boxed panels, emoji, decorative footers, ordinal numbering, or invented statistics.

Title exactly: 'Architecture overview'

Layout: Three horizontal bands separated by fine horizontal hairlines (#e3ded2), each band having its heading and a one-line muted summary on the left, and its unboxed step-by-step flow on the right connected by thin orthogonal teal arrows (#14584d).

Band 1 (top):
- Left heading: 'Scheduled trigger'
- Left summary: 'macOS launchd fires weekly ecosystem runs with user credentials'
- Right flow (each step with a deep teal #14584d outline icon):
  'launchd daemon' (underneath note: 'Weekly schedule by ecosystem') →
  'LLM Dependabot app' (underneath note: 'Holds Full Disk Access grant') →
  'Interactive login shell' (underneath note: 'zsh inherits PATH and keychain')

Band 2 (middle):
- Left heading: 'Workspace isolation'
- Left summary: 'Inspect repository prompts and isolate work in git worktrees'
- Right flow (each step with a deep teal #14584d outline icon):
  'gh discovery' (underneath note: 'Checks .github/prompts/update-deps.md') →
  'Clone or fetch' (underneath note: 'Existing checkout or ephemeral clone') →
  'Isolated git worktree' (underneath note: 'Fresh branch · working tree untouched')

Band 3 (bottom):
- Left heading: 'Agent execution & lifecycle'
- Left summary: 'Autonomous prompt run, pull request tracking, and cleanup'
- Right flow (each step with a deep teal #14584d outline icon):
  'Antigravity CLI (agy)' (underneath note: 'YOLO autonomous prompt run with timeout') →
  'Pull request opened' (underneath note: 'Atomic state update under filelock') →
  'Periodic cleanup' (underneath note: 'Prunes worktrees and deletes ephemeral clones')
```

### Execution lifecycle and isolation

- **File:** `docs/images/execution-lifecycle.webp`
- **Companion:** [`docs/images/execution-lifecycle.prompt.txt`](images/execution-lifecycle.prompt.txt)

```text
Use case: infographic-diagram. Asset type: documentation diagram for llm-dependabot, a macOS tool that runs an AI coding agent weekly to update dependencies. Landscape 3:2, flat canvas warm paper #faf8f4, ink #201d18, muted ink #5d574c, fine hairlines #e3ded2, deep teal #14584d accent for all step outline icons and connecting arrows, muted rust #9a3d2e only for failure stops. Fraunces-like serif title and band headings, Hanken-like sans labels, generous whitespace, flat outline icons in deep teal #14584d, thin orthogonal teal arrows. Match the reference style of flat warm-paper editorial documentation diagrams from indrapatil.com and python-package-quality-checks.webp. No shadows, gradients, texture, 3D, cards, boxed panels, emoji, decorative footers, ordinal numbering (do not write 'Band 1' or 'Step 1' or 'Tier 1'), or invented statistics.

Title exactly: 'Execution lifecycle and isolation'

Layout: Three horizontal bands separated by fine horizontal hairlines (#e3ded2), each band having its heading and a one-line muted summary on the left, and its unboxed step-by-step flow on the right connected by thin orthogonal teal arrows (#14584d).

Band 1 (top):
- Left heading: 'Permission boundary'
- Left summary: 'Responsible process model grants Full Disk Access to child jobs'
- Right flow (each step with a deep teal #14584d outline icon):
  'launchd daemon' (underneath note: 'Fires scheduled ecosystem group') →
  'LLM Dependabot app' (underneath note: 'Holds Full Disk Access for child tree') →
  'Interactive login shell' (underneath note: 'zsh inherits PATH & keychain credentials')

Band 2 (middle):
- Left heading: 'Repository isolation'
- Left summary: 'Safe worktree branching protects local checkouts and uncommitted work'
- Right flow (each step with a deep teal #14584d outline icon):
  'Target repository' (underneath note: 'Existing checkout or managed clone') →
  'Dedicated git worktree' (underneath note: 'Fresh branch off default branch') →
  'Untouched checkout' (underneath note: 'Active branch & uncommitted changes safe')

Band 3 (bottom):
- Left heading: 'State & automated cleanup'
- Left summary: 'Atomic concurrency locking, pull request tracking, and pruning'
- Right flow (each step with a deep teal #14584d outline icon):
  'filelock concurrency' (underneath note: 'Serialises scheduled runs & cleanup') →
  'Atomic state tracking' (underneath note: 'Records pending PRs in state.json') →
  'Automated pruning' (underneath note: 'Deletes worktree & ephemeral clone on merge')
```

### Development toolchain and tech stack

- **File:** `docs/images/tech-stack.webp`
- **Companion:** [`docs/images/tech-stack.prompt.txt`](images/tech-stack.prompt.txt)

```text
Use case: infographic-diagram. Asset type: documentation diagram for llm-dependabot, a macOS tool that runs an AI coding agent weekly to update dependencies. Landscape 3:2, flat canvas warm paper #faf8f4, ink #201d18, muted ink #5d574c, fine hairlines #e3ded2, deep teal #14584d accent for all step outline icons and connecting arrows, muted rust #9a3d2e only for failure stops. Fraunces-like serif title and band headings, Hanken-like sans labels, generous whitespace, flat outline icons in deep teal #14584d, thin orthogonal teal arrows. Match the reference style of flat warm-paper editorial documentation diagrams from indrapatil.com and python-package-quality-checks.webp. No shadows, gradients, texture, 3D, cards, boxed panels, emoji, decorative footers, ordinal numbering (do not write 'Band 1' or 'Step 1' or 'Tier 1'), or invented statistics.

Title exactly: 'Development toolchain and tech stack'

Layout: Three horizontal bands separated by fine horizontal hairlines (#e3ded2), each band having its heading and a one-line muted summary on the left, and its unboxed step-by-step flow on the right connected by thin orthogonal teal arrows (#14584d).

Band 1 (top):
- Left heading: 'Runtime & dependencies'
- Left summary: 'Single-file Python 3.15 script with locked inline dependencies'
- Right flow (each step with a deep teal #14584d outline icon):
  'Python 3.15' (underneath note: 'Modern language runtime') →
  'uv script metadata' (underneath note: 'PEP 723 inline dependencies') →
  'Locked dependencies' (underneath note: 'llm_dependabot.py.lock · frozen deps')

Band 2 (middle):
- Left heading: 'Libraries & native app'
- Left summary: 'Rust-backed validation, CLI tooling, and macOS launcher'
- Right flow (each step with a deep teal #14584d outline icon):
  'Typer & PyYAML' (underneath note: 'CLI commands & config parsing') →
  'Pydantic & filelock' (underneath note: 'Rust-core validation & concurrency gate') →
  'Native launcher' (underneath note: 'app/launcher.c · Full Disk Access')

Band 3 (bottom):
- Left heading: 'Hygiene & local checks'
- Left summary: 'Strict local linting, typing, git hooks, and vulnerability auditing'
- Right flow (each step with a deep teal #14584d outline icon):
  'Ruff lint & format' (underneath note: 'select = ["ALL"] · fast Rust linter') →
  'ty & audit' (underneath note: 'Script type check · uv audit OSV scan') →
  'prek git hooks' (underneath note: 'Hygiene & private repository name guard')
```

### Weekly schedule by ecosystem

- **File:** `docs/images/ecosystem-schedule.webp`
- **Companion:** [`docs/images/ecosystem-schedule.prompt.txt`](images/ecosystem-schedule.prompt.txt)

```text
Use case: infographic-diagram. Asset type: wide editorial documentation infographic for llm-dependabot explaining the weekly schedule across ecosystem groups. Landscape 3:2, flat canvas warm paper #faf8f4, ink #201d18, muted ink #5d574c, fine hairlines #e3ded2, restrained deep teal #14584d accents for line-art motifs. Fraunces-like serif title, Hanken-like sans labels, generous whitespace, crisp vector-like stroke drawing. No shadows, gradients, texture, 3D, cards, boxed panels, emoji, decorative footers, ordinal numbering, or arrows.

Title exactly: 'Weekly schedule by ecosystem'

Layout: A carefully composed horizontal strip divided into four equal panels by fine vertical hairlines (#e3ded2). Each panel has one clear line-art motif in deep teal #14584d at the top, a bold heading below, and a one-line muted summary underneath, in this exact left-to-right order:

Panel 1:
- Motif: Capital 'R' inside a clean package box outline
- Heading: 'R'
- Note: 'Monday 11:00 · R packages'

Panel 2:
- Motif: Two interconnected workflow nodes beside a branch icon
- Heading: 'Workflows'
- Note: 'Tuesday 11:00 · Meta & default'

Panel 3:
- Motif: Python snake logo outline beside a terminal prompt
- Heading: 'Python'
- Note: 'Wednesday 14:30 · Python packages'

Panel 4:
- Motif: Browser window outline with code tags
- Heading: 'Web'
- Note: 'Thursday 11:00 · JS, TS & frameworks'
```
