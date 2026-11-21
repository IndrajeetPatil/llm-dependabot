# Documentation illustrations

Prompts for generated figures in these docs, recorded so the next figure can
start from them. The rules are in [DESIGN.md](../../DESIGN.md#documentation-illustrations),
and the [documentation-illustrations skill](../../.agents/skills/documentation-illustrations/SKILL.md)
explains how to write a prompt.

The hex sticker is drawn by hand; see [hextools](../../hextools/README.md).

## Catalogue

| Figure | Subject | Embedded in |
| --- | --- | --- |
| [`architecture-overview.webp`](architecture-overview.webp) | Scheduled trigger, worktree isolation, and agent lifecycle | [README.md](../../README.md), [architecture.md](../architecture.md) |
| [`giga-factory.webp`](giga-factory.webp) | The schedule coordinating a software factory inside each project | [README.md](../../README.md) |
| [`execution-lifecycle.webp`](execution-lifecycle.webp) | Permission boundary, repository isolation, and state locking | [architecture.md](../architecture.md) |
| [`tech-stack.webp`](tech-stack.webp) | Runtime, dependencies, core libraries, and local QA checks | [development.md](../development.md) |
| [`ecosystem-schedule.webp`](ecosystem-schedule.webp) | Configured project-group schedules, prompt cadence, and pull-request cleanup | [configuration.md](../configuration.md) |
| [`multiple-prompts.webp`](multiple-prompts.webp) | The same isolated run pattern for each due prompt, with room for more prompts | [configuration.md](../configuration.md) |
| [`process-and-run.webp`](process-and-run.webp) | Responsible process tree and per-repository run | [architecture.md](../architecture.md) |
| [`usage-overview.webp`](usage-overview.webp) | Status, on-demand runs, pull requests, and cleanup | [usage.md](../usage.md) |
| [`setup-checklist.webp`](setup-checklist.webp) | Local setup choices, repository opt-in, prompt conventions, and project readiness | [setup.md](../setup.md) |

## Prompts

### Architecture overview

- **File:** `docs/images/architecture-overview.webp`
- **Companion:** [`architecture-overview.prompt.txt`](architecture-overview.prompt.txt)

```text
Create a NEW documentation infographic, using the supplied image only as a reference for its warm-paper palette, restrained editorial layout, serif title, precise thin icon strokes, and generous whitespace. It must clearly show this specific llm-dependabot architecture, not copy any existing text or arrangement. Landscape 3:2. Flat warm-paper background #faf8f4, ink #201d18, muted ink #5d574c, hairlines #e3ded2, restrained teal #14584d only on the active flow. Fraunces-like serif title and band headings, Hanken-like sans labels, generous whitespace, flat outline icons, thin orthogonal arrows. Use an accurate small Apple silhouette to identify the macOS app and an authentic GitHub Octocat silhouette to identify repository discovery. Do not invent or approximate other brand marks; generic icons for scheduler, shell, worktree, coding agent, pull request, and cleanup are fine. Do not include a fake App Store mark. Ensure labels are legible, correctly spelled, exact wording below. Band one heading “Scheduled on your Mac”, summary “Weekly launchd jobs run with your login credentials”: nodes “launchd” → “LLM Dependabot app” (small note “Full Disk Access”) → “Login shell” (small note “zsh · PATH · keychain”). Band two heading “Repositories stay isolated”, summary “Matching prompts start work in a dedicated worktree”: nodes “GitHub discovery” (small note “Checks each repository prompt”) → “Clone or fetch” → “Git worktree” (small note “Fresh branch · checkout untouched”). Band three heading “Agent opens a pull request”, summary “The run is tracked and cleaned up after review”: nodes “Coding Agent” (small note “Runs the repository prompt”) → “Pull request” (small note “Pending state is recorded”) → “Cleanup” (small note “Removes worktree after merge or close”). Thin orthogonal arrows, no crossing, no cards or boxed panels, no shadows, gradients, texture, 3D, emojis, decorative footer, ordinal numbers, or extra text. Keep line breaks and alignment polished. Use British English.
```

**Palette correction edit prompt:**

```text
Preserve this architecture infographic’s composition, wording, icons, arrows, and warm-paper editorial design. Harmonize every teal line, symbol, and arrow to the light-mode base accent from the design guide: #14584d (RGB 20, 88, 77). Use no brighter turquoise or accent-light teal. Anti-aliased edge pixels may blend between this teal and the paper, but flat stroke interiors should match #14584d. Keep all headings in ink #201d18, explanatory copy in muted ink #5d574c, and hairlines in #e3ded2. Preserve the Apple and GitHub silhouettes as simple single-colour marks in the same base teal; do not invent brand colours. Make no other changes.

Agent-neutral label edit prompt:

Replace only “Antigravity CLI” with “Coding Agent” so the diagram remains accurate if the default coding agent changes. Preserve every other label, icon, arrow, layout, colour, and style.
```
### Software Giga Factory

- **File:** `docs/images/giga-factory.webp`
- **Companion:** [`giga-factory.prompt.txt`](giga-factory.prompt.txt)

```text
Use case: infographic-diagram. Asset type: README overview illustration for llm-dependabot, a scheduler that runs repository-owned coding prompts with an agent. Create a landscape 3:2 editorial diagram titled exactly “Software Giga Factory”. Show a hierarchy: a staggered schedule coordinates many software projects, and each project contains its own software factory. The schedule hub is the Giga Factory; the project-level development and review cycle is a factory repeated independently in each project.

Use the repository design tokens: warm paper #faf8f4, ink #201d18, muted ink #5d574c, hairlines #e3ded2, and restrained teal #14584d for technology icons and active paths. Use Fraunces-like serif headings, Hanken-like sans labels, flat outline icons, precise arrows, and generous whitespace. Keep official Python and R logos in their official colours. No shadows, gradients, texture, 3D, cards, emoji, decorative footer, or invented statistics. Keep text legible at README width.

Subtitle exactly: “A staggered schedule activates the software factory inside each project”

Top band heading: “A staggered schedule”. Show a calendar/clock icon and four project groups with these exact labels and marks:
- “Web Applications · Monday” with a browser/code icon
- “Python · Tuesday” with the official Python logo
- “Sundry · Wednesday” with a mixed-files icon
- “R Packages · Thursday” with the authentic R logo

Connect these groups to the project-level factory below. Use a repeated-factory motif with an ellipsis to show that many project repositories each contain their own copy of the same factory.

Lower band heading: “Each project has its own software factory”. Summary exactly: “Prompts drive dependency updates, refactoring, simplification, and more”. Show one enlarged example of the repeated project-local flow, left to right:
“Committed prompt + project guidance” → “Coding agent in isolated worktree” → “Pull request” → “Project checks” → “Maintainer review + merge” → “Updated project”.

Draw a clear feedback loop from “Project checks” and “Maintainer review” back to “Coding agent”, labelled “Findings”. This represents project-local fixes before merge; do not imply that llm-dependabot approves or merges pull requests. Keep the schedule and project-local factory as separate levels of the illustration.

Footer note exactly: “Weekly group schedules; monthly prompts run when due; one repository and due prompt at a time”. Do not show Mac, Apple, launchd, shell commands, private repository names, credentials, or exact monthly dates. Ensure every label is spelled exactly, arrows are clear, and the repeated project-local software factory is unmistakable. British English.

**Follow-up edit prompt:** Preserve the whole illustration and change only the summary beneath “Each project has its own software factory”. Replace it with exactly: “Prompts drive dependency updates, refactoring, simplification, and more”. Keep all other text and visual elements unchanged.
```

### Process and run

- **File:** `docs/images/process-and-run.webp`
- **Companion:** [`process-and-run.prompt.txt`](process-and-run.prompt.txt)

```text
Create a landscape 3:2 editorial documentation infographic for llm-dependabot. Use warm paper #faf8f4, ink #201d18, muted #5d574c, hairlines #e3ded2, sparse teal #14584d for work paths, and muted rust #9a3d2e for a stop. Use Fraunces-like serif headings, Hanken-like sans labels, flat outline icons, and no cards, shadows, gradients, texture, 3D, emoji, or decorative footer. Title “Process and run”.

In the “Responsible process” band, show “launchd” → “LLM Dependabot app” → “Login shell” → “Update scheduler” → “Coding agent”. Explain Full Disk Access under the app, the user's login environment under the shell, and a separate Git worktree under the coding agent.

In the “One repository run” band, show “Discover repository and prompt” → decision “Project copy exists?” with branches “Yes → Update existing copy” and “No → Prepare a new copy”; both rejoin at “Create Git worktree” → “Run coding agent with a time limit” → decision “Pull request opened?” with branches “Yes → Record pending state” and “No → Remove worktree”. Add “Failures are logged; the next repository still runs”. Keep the arrows and branch directions clear.

Do not use literal commands, CLI names, flags, variables, filenames, or shell syntax. British English.
```



**Edit prompts:**

```text
Replace all shell and script invocations with the plain-language process labels “Login shell”, “Update scheduler”, and “Coding agent”. Describe the login environment and Git worktree in the supporting notes.

Replace implementation-level repository operations with “Project copy exists?”, “Update existing copy”, “Prepare a new copy”, “Create Git worktree”, and “Run coding agent with a time limit”. Use “Remove worktree” as the no-pull-request outcome. Preserve branch direction and other labels.

Clarify the separate checkout as a Git worktree. Use “Runs in a Git worktree”, “Create Git worktree”, and “Remove worktree” for that checkout.

Preserve this process infographic’s composition, wording, icons, arrows, branches, and warm-paper editorial design. Harmonize every teal line, symbol, and arrow to the light-mode base accent from the design guide: #14584d (RGB 20, 88, 77). Use no brighter turquoise or accent-light teal. Anti-aliased edge pixels may blend between this teal and the paper, but flat stroke interiors should match #14584d. Keep all headings in ink #201d18, explanatory copy in muted ink #5d574c, and hairlines in #e3ded2. Make no other changes.
```
### Usage overview

- **File:** `docs/images/usage-overview.webp`
- **Companion:** [`usage-overview.prompt.txt`](usage-overview.prompt.txt)

```text
Create a landscape 3:2 editorial documentation infographic for the llm-dependabot usage guide. Use warm paper #faf8f4, ink #201d18, muted ink #5d574c, hairlines #e3ded2, and restrained teal #14584d. Use a Fraunces-like serif title, Hanken-like sans labels, generous whitespace, flat outline icons, and no cards, shadows, gradients, texture, 3D, emoji, or decorative footer. Title “Using llm-dependabot”.

Show three sections. “Check the schedule”: “Schedule status” → “Project groups”. “Run work on demand”: “Preview Python group” → “Run Python group” → “Pull request”, with the accurate official Python logo beside both Python group labels. Add the branch “Choose one project” from the run action. “Finish the lifecycle”: “Review and merge or close PR” → “Scheduled cleanup” → “Worktree removed”, with the note “Runs periodically”.

Use a recognizable GitHub mark beside Pull request. No literal commands, parameters, filenames, or configuration keys. Keep labels legible, spelling exact, and the arrows correct. British English.
```



**Edit prompts:**

```text
Edit the usage infographic to replace literal command and parameter labels with “Preview Python group”, “Run Python group”, “Choose one project”, and “Runs periodically”. Add a small accurate Python logo beside each Python group label.

Refine the schedule section to use “Schedule status” and “Project groups”. Keep the Python group flow and GitHub mark, preserve the single-project branch, and label the final item “Worktree removed”. Keep the cleanup cadence at the higher level “Runs periodically”. Remove all code syntax and configuration names.

Use “Worktree removed” for the final item because scheduled cleanup removes the isolated Git worktree. Keep “Scheduled cleanup” and “Runs periodically” unchanged.

Preserve the usage infographic’s layout, wording, arrows, all icons, and warm-paper editorial design. Set all teal line icons, arrows, and teal marks to the light-mode base accent #14584d (RGB 20, 88, 77), with no brighter turquoise or accent-light teal. Anti-aliased edges may blend between #14584d and the paper background, but flat stroke interiors should match the base accent. Keep headings in ink #201d18, supporting labels in muted ink #5d574c, and hairlines #e3ded2. Preserve both official Python logos in their correct blue and yellow colours; do not recolour them. Preserve the GitHub mark as a single-colour mark in the base accent. Do not alter any wording, spacing, or content.

Divider-alignment edit prompt:

Align all three thin vertical dividers between the left icon-and-summary column and the right-side flow on the same vertical x-position. Match the top and middle divider positions by moving only the bottom divider horizontally. Preserve divider lengths and vertical placement. Do not change any wording, icons, arrows, spacing elsewhere, colours, typography, or other layout elements.

Bottom-row spacing edit prompt:

Keep all three dividers aligned. In the final row only, shift the complete right-hand flow, including labels, icons, arrows, and subtitle, about 24 pixels right while preserving its content and positions relative to one another. Keep the divider fixed and leave the left title, icon, heading, and summary unchanged. This gives the first flow label more breathing room after the divider. Keep the last node inside the canvas margin.
```
### Execution lifecycle and isolation

- **File:** `docs/images/execution-lifecycle.webp`
- **Companion:** [`execution-lifecycle.prompt.txt`](execution-lifecycle.prompt.txt)

```text
Restyle the first supplied image, “Execution lifecycle and isolation”, to follow the second supplied image, “How llm-dependabot works”. The second image is the visual style reference; the first is the factual content to revise. Match its warm editorial page, exact light palette, large elegant high-contrast serif title, smaller serif section headings, clean Hanken-like sans labels, thin flat line drawings, delicate orthogonal arrows, generous whitespace, and fine hairline separators. Use paper #faf8f4, ink #201d18, muted ink #5d574c, hairlines #e3ded2, and base teal #14584d only for the path and line icons. No bright turquoise, heavy icons, bold/condensed sans type, shadows, gradients, texture, cards, 3D, or decorative footer. Keep a landscape 3:2 canvas, three horizontal bands, with each band's heading and muted one-line summary on the left and its flow on the right. Keep all text clear at documentation width.

Use this exact content, with no other wording:

Title: “Execution lifecycle and isolation”.

Band 1 heading “Permission boundary”. Summary “Full Disk Access follows the responsible app process”. Flow: “launchd” → “LLM Dependabot app” (note “Full Disk Access”) → “Login shell” (note “Uses your login environment”).

Band 2 heading “Repository isolation”. Summary “Dedicated branches protect existing checkouts”. Flow: “Target repository” (note “Existing checkout or managed clone”) → “Git worktree” (note “Fresh branch from default”) → “Original checkout” (note “Active branch and uncommitted work stay untouched”).

Band 3 heading “Run tracking and cleanup”. Summary “Runs stay coordinated until pull requests finish”. Flow: “Run coordination” (note “Scheduled work does not overlap”) → “Pending pull request” (note “Tracked for review”) → “Automated cleanup” (note “Removes local worktree and run branch after merge or close”).

Use simple elegant outline symbols matching the reference illustration style: clock/scheduler, app shield, terminal, repository, Git branch/worktree, untouched checkout, coordination lock, pending pull request document, and cleanup brush or pruning tool. Preserve clear left-to-right arrows. Use exact spelling and British English. Do not include implementation identifiers such as filelock or state.json.
```

**Palette correction edit prompt:**

```text
Preserve this architecture infographic’s composition, wording, icons, arrows, and warm-paper editorial design. Harmonize every teal line, symbol, and arrow to the light-mode base accent from the design guide: #14584d (RGB 20, 88, 77). Use no brighter turquoise or accent-light teal. Anti-aliased edge pixels may blend between this teal and the paper, but flat stroke interiors should match #14584d. Keep all headings in ink #201d18, explanatory copy in muted ink #5d574c, and hairlines #e3ded2. Make no other changes.

Style-match edit prompt:

Restyle the execution-lifecycle illustration to match architecture-overview.webp: elegant serif title and section headings, restrained Hanken-like labels, delicate flat outline icons, warm-paper background, thin hairlines, generous whitespace, and base teal #14584d. Preserve the facts and wording, while using the supplied high-level labels. Do not use the heavier icons or dense technical typography from the earlier rendering.
```
### Development toolchain and tech stack

- **File:** `docs/images/tech-stack.webp`
- **Companion:** [`tech-stack.prompt.txt`](tech-stack.prompt.txt)

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

**Palette correction edit prompt:**

```text
Preserve this development infographic’s composition, wording, icons, arrows, bands, and warm-paper editorial design. Harmonize every teal line, icon, and arrow to the light-mode base accent from the design guide: #14584d (RGB 20, 88, 77). Use no brighter turquoise or accent-light teal. Anti-aliased edge pixels may blend between this teal and the paper, but flat stroke interiors should match #14584d. Keep headings in ink #201d18, explanatory copy in muted ink #5d574c, and hairlines #e3ded2. Preserve recognizable third-party brand marks in their official colours where shown. Make no other changes.
```
### Configured project groups and prompt cadence

- **File:** `docs/images/ecosystem-schedule.webp`
- **Companion:** [`ecosystem-schedule.prompt.txt`](ecosystem-schedule.prompt.txt)

```text
Use case: infographic-diagram. Asset type: documentation diagram for llm-dependabot, a macOS tool that runs repository-owned coding prompts on a schedule. Revise the supplied schedule infographic to reflect the current configuration while preserving its warm-paper editorial style, generous whitespace, serif title, clear sans-serif labels, and fine row dividers. Landscape 3:2. Use background #faf8f4, ink #201d18, muted ink #5d574c, hairlines #e3ded2, and teal #14584d for technology icons. Preserve the authentic R and Python logos in their official colours. No shadows, gradients, texture, 3D, cards, emoji, decorative footer, invented facts, or private repository names.

Title: “Configured project groups and prompt cadence”
Subtitle: “Each group starts weekly; prompts run when due”

Show five aligned rows with these exact labels and details, in weekday order:
- “Web Applications”, note “TypeScript · JavaScript · Astro · Svelte · Vue · HTML · CSS”, schedule “Monday · 11:00”, cadence “update-deps weekly · simplify-codebase monthly”. Use a teal browser/code icon.
- “Python”, note “Python”, schedule “Tuesday · 11:00”, cadence “update-deps weekly · simplify-codebase monthly”. Use the official Python logo in its blue and yellow.
- “Sundry”, note “Unmatched project types”, schedule “Wednesday · 11:00”, cadence “update-deps weekly · simplify-codebase monthly”. Use a teal mixed-collection icon such as a simple toolkit with varied file symbols.
- “R Packages”, note “R projects”, schedule “Thursday · 11:00”, cadence “update-deps monthly · simplify-codebase monthly”. Use the authentic R logo in its official colours.
- “Pull-request cleanup”, note “Removes worktrees and local branches after PRs merge or close”. Use a teal pruning brush or pruning shears icon, visibly distinct from the Sundry mixed-collection icon. Do not state a cleanup interval.

Keep every row aligned with consistent dividers and margins. Keep the weekday and time text legible. Keep technology icons teal #14584d, with the R and Python logos as official-colour exceptions. Spell all labels exactly as written. British English.

**Follow-up edit prompt:** Replace the internal group labels “web” and “workflows” with reader-facing labels “Web Applications” and “Sundry”; use “Unmatched project types” as the Sundry note. Keep all schedules, cadence labels, colours, and layout unchanged. Replace the Sundry branching icon with a teal mixed-collection/toolkit icon and replace the Pull-request cleanup branching icon with teal pruning shears, clearly distinguishing the two. Keep the R and Python logos in official colours.

**Capitalisation edit prompt:** Change only lowercase “python” to “Python” in the group label. Preserve every other text, logo, icon, colour, spacing, and layout element.
```

### One schedule, multiple prompts

- **File:** `docs/images/multiple-prompts.webp`
- **Companion:** [`multiple-prompts.prompt.txt`](multiple-prompts.prompt.txt)

```text
Use case: infographic-diagram. Asset type: documentation diagram for llm-dependabot, a macOS tool that runs repository-owned coding prompts on a schedule. Create a new landscape 3:2 editorial infographic in a warm-paper documentation style: background #faf8f4, ink #201d18, muted ink #5d574c, fine hairlines #e3ded2, sparse base teal #14584d for the explained path. Use a Fraunces-like serif title and section headings, Hanken-like sans labels, generous whitespace, flat outline icons, and thin orthogonal arrows. Match the restrained visual language of the llm-dependabot documentation figures. No shadows, gradients, texture, 3D, cards, boxed panels, emoji, decorative footer, ordinal numbering, or invented facts.

Title exactly: “One schedule, multiple prompts”
Subtitle exactly: “Each due prompt gets its own isolated run”

Show one short context line below the subtitle: “At each weekly group run, process prompts present in the repository when due” and a small muted note “One prompt at a time”.

Then show three spacious horizontal rows, separated by fine hairlines. Each row repeats the same clear left-to-right flow with the exact labels and no branching:
Row one: “update-deps” (small cadence note “Weekly”) → “Own Git worktree + branch” → “Coding agent runs this prompt” → “Its own pull request”
Row two: “simplify-codebase” (small cadence note “Monthly, when due”) → “Own Git worktree + branch” → “Coding agent runs this prompt” → “Its own pull request”
Row three: “…” (small note “Other configured prompts”) → “Own Git worktree + branch” → “Coding agent runs this prompt” → “Its own pull request”

Use a file/page outline icon for prompt labels, a separate-branch/worktree outline for each worktree, a simple agent/terminal outline, and a pull-request branching icon. Make it visually obvious that every prompt row repeats the same setup and creates a separate pull request. Use thin arrows that do not cross. Do not imply that prompts run in parallel. Preserve the literal ellipsis “…” as shown. Ensure all wording, arrow direction, and spelling are exact and legible at documentation width. British English.
```
