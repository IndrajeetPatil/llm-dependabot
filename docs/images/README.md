# Documentation illustrations

Prompts for generated figures in these docs, recorded so the next figure can
start from them. The rules are in [DESIGN.md](../../DESIGN.md#documentation-illustrations),
and the [documentation-illustrations skill](../../.agents/skills/documentation-illustrations/SKILL.md)
explains how to write a prompt.

The hex sticker is drawn by hand; see [hextools](../../hextools/README.md).

## Catalogue

| Figure | Subject | Embedded in |
| --- | --- | --- |
| [`architecture-overview.webp`](architecture-overview.webp) | Scheduled trigger, due-prompt discovery, worktree isolation, and agent lifecycle | [README.md](../../README.md), [architecture.md](../architecture.md) |
| [`giga-factory.webp`](giga-factory.webp) | The schedule coordinating a software factory inside each project | [README.md](../../README.md) |
| [`execution-lifecycle.webp`](execution-lifecycle.webp) | Permission boundary, repository isolation, and state locking | [architecture.md](../architecture.md) |
| [`tech-stack.webp`](tech-stack.webp) | Python package, project dependencies, core libraries, local checks, and CI supply-chain checks | [development.md](../development.md) |
| [`ecosystem-schedule.webp`](ecosystem-schedule.webp) | Three shipped prompts across configured project-group schedules and pull-request cleanup | [configuration.md](../configuration.md) |
| [`multiple-prompts.webp`](multiple-prompts.webp) | The isolated run pattern for update-deps, simplify-codebase, gsc-analysis, and more | [configuration.md](../configuration.md) |
| [`process-and-run.webp`](process-and-run.webp) | Responsible process tree, prompt cadence decisions, per-prompt worktrees, and run tracking | [architecture.md](../architecture.md) |
| [`usage-overview.webp`](usage-overview.webp) | Schedule and dashboard, on-demand runs, transcripts, and cleanup | [usage.md](../usage.md) |
| [`setup-checklist.webp`](setup-checklist.webp) | Local setup choices, repository opt-in, prompt conventions, and project readiness | [setup.md](../setup.md) |
| [`autonomous-evolution.webp`](autonomous-evolution.webp) | Signal, prompt, agent, checks, review, merge, production, and feedback | [autonomy.md](../autonomy.md) |
| [`learn-from-mistakes.webp`](learn-from-mistakes.webp) | Code and guidance fixes converge on the same gates and review | [autonomy.md](../autonomy.md) |

## Prompts

### Autonomous evolution

- **File:** `docs/images/autonomous-evolution.webp`
- **Companion:** [`autonomous-evolution.prompt.txt`](autonomous-evolution.prompt.txt)



```text
Use case: infographic-diagram. Asset type: documentation illustration for the “Autonomous evolution” guide. Create a new landscape 3:2 editorial diagram showing the autonomous delivery feedback loop. Use warm paper #faf8f4, ink #201d18, muted ink #5d574c, fine hairlines #e3ded2, and restrained teal #14584d for the flow. Use a large Fraunces-like serif title, Hanken-like sans labels, flat outline icons, thin orthogonal arrows, generous whitespace, and no cards, shadows, gradients, texture, 3D, emoji, decorative footer, ordinal numbering, extra text, invented facts, or logos. British English.

Title exactly “Autonomous evolution”.

Show a left-to-right flow: “Signal” (note “New releases, code smells, search, or monitoring reports”) → “Committed prompt” (note “Due on schedule”) → “Coding agent” (note “Isolated worktree”) → “Pull request” (note “Evidence included”) → “Quality gates” (note “Verification harness”) → “Independent reviewer” → “Squash-merge” → “Production”.

Draw a failure loop from Quality gates back to Coding agent labelled “Failures”; a findings loop from Independent reviewer back to Coding agent labelled “Findings”; and an approval arrow from Independent reviewer to Squash-merge labelled “Approval”. Draw a return loop from Production to Signal. Use a friendly flat outline robot for Coding agent and another robot with simple glasses for Independent reviewer. Use a software-package outline icon for Production. Keep arrows distinct and avoid crossings.
```
### Learn from mistakes

- **File:** `docs/images/learn-from-mistakes.webp`
- **Companion:** [`learn-from-mistakes.prompt.txt`](learn-from-mistakes.prompt.txt)



```text
Use case: infographic-diagram. Asset type: documentation illustration for the “Autonomous evolution” guide. Input image: use the existing llm-dependabot illustration only as reference for its warm-paper palette, editorial typography, fine separators, restrained teal linework, and whitespace. Create a new illustration about learning from mistakes; do not copy the reference content or arrangement. Landscape 3:2. Title exactly: “Learn from mistakes”. Use warm paper #faf8f4, ink #201d18, muted ink #5d574c, fine hairlines #e3ded2, restrained teal #14584d, large Fraunces-like serif title, Hanken-like sans labels, flat outline icons, fine orthogonal arrows, and no cards. Show this flow: “Failing check, review finding, or regression” → “Trace the cause” → split into two parallel paths: “Fix the code” and “Fix the guidance” (small note: “AGENTS.md, a skill or its assets, or a prompt”). Both paths converge on “Same quality gates and review” → “Later runs avoid the mistake”. Use readable branch and rejoin arrows with no crossed lines; make clear that both code and guidance fixes go through the same quality gates and review before later runs avoid repeating the mistake. Exact wording, spelling, and punctuation as given. British English. No shadows, gradients, texture, 3D, cards, emoji, footer, ordinal numbering, extra text, invented facts, or logos.
```
### Architecture overview

- **File:** `docs/images/architecture-overview.webp`
- **Companion:** [`architecture-overview.prompt.txt`](architecture-overview.prompt.txt)




```text
Use case: infographic-diagram. Asset type: documentation infographic showing how llm-dependabot works. Create a landscape 3:2 illustration with warm paper #faf8f4, ink #201d18, muted ink #5d574c, hairlines #e3ded2, restrained teal #14584d, Fraunces-like serif title and band headings, Hanken-like sans labels, generous whitespace, and thin orthogonal arrows. Use an accurate Apple silhouette for the macOS app and an authentic GitHub Octocat for discovery; keep marks simple and single-colour teal. Generic outline icons are suitable for scheduler, shell, worktree, agent, pull request, and cleanup. No fake App Store mark, shadows, gradients, texture, 3D, cards, emoji, decorative footer, ordinal numbers, or invented text. British English.

Title “How llm-dependabot works”.

Band “Scheduled on your Mac”, summary “Weekly launchd jobs run with your login credentials”: “launchd” → “LLM Dependabot app” (note “Full Disk Access”) → “Login shell” (note “zsh · PATH · keychain”).

Band “Repositories stay isolated”, summary “Each due prompt starts work in its own worktree”: “GitHub discovery” (note “Finds committed prompts and which are due”) → “Clone or fetch” → “Git worktree” (note “Fresh branch · checkout untouched”).

Band “Agent opens a pull request”, summary “The run is tracked and cleaned up after review”: “Coding Agent” (note “Runs the repository prompt”) → “Pull request” (note “Pending state is recorded”) → “Cleanup” (note “Removes worktree after merge or close”).

Keep the three horizontal bands aligned, with summaries left and flows right. Exact text and spelling.
```
### Software Giga Factory

- **File:** `docs/images/giga-factory.webp`
- **Companion:** [`giga-factory.prompt.txt`](giga-factory.prompt.txt)



```text
Use case: infographic-diagram. Asset type: README overview illustration for llm-dependabot, a scheduler that runs repository-owned coding prompts with an agent. Create a landscape 3:2 editorial diagram titled exactly “Software Giga Factory”. Use docs/images/architecture-overview.webp, “How llm-dependabot works”, as the visual style reference: warm paper #faf8f4, ink #201d18, muted ink #5d574c, hairlines #e3ded2, restrained teal #14584d, Fraunces-like serif headings, Hanken-like sans labels, flat single-colour outline icons, thin orthogonal arrows, and generous whitespace. Match its restrained typography, linework, separators, and clear band hierarchy. Use monochrome teal outline interpretations of the Python and R marks, never their colourful official marks. No shadows, gradients, texture, 3D, cards, emoji, decorative footer, or invented statistics. Keep text legible at README width. British English.

Title exactly “Software Giga Factory”. Subtitle exactly “A staggered schedule activates the software factory inside each project”. Show a hierarchy: a staggered schedule coordinates many software projects, and each project contains its own software factory. The schedule hub is the Giga Factory; the project-level development and review cycle is a factory repeated independently in each project.

Use two distinct horizontal bands separated by fine hairlines. Put each serif band heading and its one-line muted summary at the left, with its flow on the right, following the reference illustration's spacious editorial layout.

Top band “A staggered schedule”: show a calendar/clock icon and four project groups: “Web Applications · Monday” with a browser/code icon; “Python · Tuesday” with a monochrome teal outline Python mark; “Sundry · Wednesday” with a mixed-files icon; and “R Packages · Thursday” with a monochrome teal outline R mark. Connect these groups to the project-level factory below. Use a repeated-factory motif with an ellipsis to show that many project repositories each contain their own copy of the same factory.

Lower band “Each project has its own software factory”, summary exactly “Prompts drive dependency updates, refactoring, simplification, and more”. Make the entire project-local factory prominent and unmistakable. Show every stage in this exact order, with a separate clear outline icon and readable label for each: “Committed prompt + project guidance” → “Coding agent in isolated worktree” → “Pull request” → “Project checks” → “Independent LLM reviewer” → “Updated project”. Show “Independent LLM reviewer” with a friendly outline robot with simple glasses. Draw clear feedback loops from both “Project checks” and “Independent LLM reviewer” back to “Coding agent in isolated worktree”, labelled “Findings”. This represents project-local fixes before merge; llm-dependabot does not approve or merge pull requests. Keep the scheduled groups and project-local factory as separate levels.

Footer note exactly “Weekly group schedules; monthly prompts run when due; one repository and due prompt at a time”. Do not show Mac, Apple, launchd, shell commands, private repository names, credentials, or exact monthly dates. Ensure every label is exact, spelling is correct, arrows are distinct and clear, and all factory stages are visible at README width.
```
### Process and run

- **File:** `docs/images/process-and-run.webp`

- **Companion:** [`process-and-run.prompt.txt`](process-and-run.prompt.txt)


```text
Use case: infographic-diagram. Asset type: documentation diagram for llm-dependabot's process tree and per-repository run. Create a landscape 3:2 editorial infographic with warm paper #faf8f4, ink #201d18, muted ink #5d574c, fine hairlines #e3ded2, sparse teal #14584d, and muted rust #9a3d2e for the worktree-removal icon. Use Fraunces-like serif title and band headings, Hanken-like sans labels, flat outline icons, and thin orthogonal arrows. Two horizontal bands, no cards, shadows, gradients, texture, 3D, emoji, or decorative footer. British English.

Title exactly “Process and run”.

Top band “Responsible process”: “launchd” → “LLM Dependabot app” (note “Responsible process · Full Disk Access”) → “Login shell” (note “Uses the user's login environment”) → “uv run llm-dependabot” → “Coding agent” (note “Runs in a Git worktree”). Branch from “uv run llm-dependabot” to “caffeinate” with note “keeps the Mac awake”.

Bottom band “One repository run”: “Discover repository and prompt” → decision “Prompt due?” (note “weekly, or monthly not yet run this month”). “No” leads to “Skip”. “Yes” continues to decision “Project copy exists?” with “Yes → Update existing copy” and “No → Prepare a new copy”; rejoin at “Create Git worktree” → “Run coding agent with a time limit” → decision “Pull request opened?”. Yes branch: “Record pending state” → “Record run date”. No branch: “Remove worktree” → “Record run date”. Put the note “Every completed run counts towards the cadence” beside the date outcomes. Mark the segment “Create Git worktree” → agent → pull-request decision as repeating for each due prompt in the repository. Add muted note “Pull requests are labelled while the agent works” inside the dashed repeat area, below the coding-agent node. Footer exactly “Failures are logged and not recorded; the next prompt or repository still runs”. Make all branches distinct, non-crossing, and legible.
```
### Usage overview

- **File:** `docs/images/usage-overview.webp`

- **Companion:** [`usage-overview.prompt.txt`](usage-overview.prompt.txt)


```text
Use case: infographic-diagram. Asset type: documentation infographic for the llm-dependabot usage guide. Create a landscape 3:2 editorial infographic with warm paper #faf8f4, ink #201d18, muted ink #5d574c, hairlines #e3ded2, restrained teal #14584d, Fraunces-like serif headings, Hanken-like sans labels, generous whitespace, flat outline icons, and no cards, shadows, gradients, texture, 3D, emoji, or decorative footer. British English.

Title “Using llm-dependabot”. Show three sections:
- “Check the schedule and history”, summary “See upcoming groups, past runs, and pending pull requests”: “Schedule status” → “Dashboard” (note “Upcoming schedule · run history · transcripts”).

- “Run work on demand”, summary “Preview first or start a group or repository”: “Preview Python group” → “Run Python group” → “Pull request”. Add branch “Choose one project or one prompt” with muted note “REPO= / PROMPT=”. Draw recognisable Python marks beside both Python group labels as flat, single-colour teal outline icons without blue or yellow fills. Keep the GitHub mark accurate, single-colour teal, and secondary to its Pull request label.

- “Finish the lifecycle”, summary “Review pull requests; cleanup handles finished work”: “Review and merge or close PR” → “Scheduled cleanup” → “Worktree and run-only clone removed”. Add muted note “Agent transcripts in ~/Library/Logs/llm-dependabot”.

Keep text and arrows exact, legible, and correctly directed.
```
### Execution lifecycle and isolation

- **File:** `docs/images/execution-lifecycle.webp`
- **Companion:** [`execution-lifecycle.prompt.txt`](execution-lifecycle.prompt.txt)



```text
Use case: infographic-diagram. Asset type: documentation infographic for the architecture guide. Create a landscape 3:2 diagram with warm paper #faf8f4, ink #201d18, muted ink #5d574c, fine hairlines #e3ded2, and base teal #14584d for path and line icons. Use elegant Fraunces-like serif title and band headings, restrained Hanken-like sans labels, delicate flat outline icons, thin orthogonal arrows, generous whitespace, and three horizontal bands with heading and summary on the left and flow on the right. No bright turquoise, heavy icons, bold or condensed sans type, shadows, gradients, texture, cards, 3D, or decorative footer. Keep labels legible at documentation width. British English.

Title “Execution lifecycle and isolation”.

Band “Permission boundary”, summary “Full Disk Access follows the responsible app process”: “launchd” → “LLM Dependabot app” (note “Full Disk Access”) → “Login shell” (note “Uses your login environment”).

Band “Repository isolation”, summary “Dedicated branches protect existing checkouts”: “Target repository” (note “Existing checkout or managed clone”) → “Git worktree” (note “Fresh branch from default”) → “Original checkout” (note “Active branch and uncommitted work stay untouched”).

Band “Run tracking and cleanup”, summary “Runs stay coordinated until pull requests finish”: “Run coordination” (note “Scheduled work does not overlap”) → “Pending pull request” (note “Tracked for review”) → “Automated cleanup” (note “Removes local worktree and run branch after merge or close”).

Use a clock, app shield, terminal, repository, Git worktree, untouched checkout, coordination lock, pull-request document, and cleanup brush icons. Preserve the clear left-to-right flow. Do not include implementation identifiers such as filelock or state.json.
```
### Development toolchain and tech stack

- **File:** `docs/images/tech-stack.webp`

- **Companion:** [`tech-stack.prompt.txt`](tech-stack.prompt.txt)


```text
Use case: infographic-diagram. Asset type: documentation diagram for llm-dependabot's development toolchain. Create a landscape 3:2 editorial infographic using warm paper #faf8f4, ink #201d18, muted ink #5d574c, fine hairlines #e3ded2, and sparse teal #14584d. Use Fraunces-like serif title and band headings, Hanken-like sans labels, generous whitespace, flat outline icons, and thin orthogonal arrows. Keep the flow unboxed, with four horizontal bands separated by hairlines. No shadows, gradients, texture, 3D, cards, emoji, decorative footer, ordinal numbering, or invented facts. British English.

Title exactly: “Development toolchain and tech stack”

Band “Runtime & dependencies”, summary “Python package and locked project dependencies”: “Python 3.15” (note “Modern language runtime”) → “llm_dependabot package” (note “src/llm_dependabot/”) → “uv project” (note “pyproject.toml · uv.lock”).

Band “Libraries & native app”, summary “Rust-backed validation, CLI tooling, and macOS launcher”: “Typer & PyYAML” (note “CLI commands & config parsing”) → “Pydantic & filelock” (note “Rust-core validation & concurrency gate”) → “Native launcher” (note “app/launcher.c · Full Disk Access”).

Band “Hygiene & local checks”, summary “Strict local linting, typing, dependency auditing, and git hooks”: “Ruff lint & format” (note “select = ["ALL"] · fast Rust linter”) → “ty, pyrefly & unref” (note “Type check · type coverage · dead code”) → “uv audit & deptry” (note “OSV scan · declared dependencies”) → “prek git hooks” (note “Hygiene & private repository name guard”).

Band “CI and supply chain”, summary “The same checks again on every pull request, with pinned actions”: “GitHub Actions workflows” (note “Zensical docs site”) → “actionlint and zizmor” (note “zizmor (pedantic)”) → “Gitleaks” (note “Scans the full history”) → “actions.lock” (note “gh-actions-lock”). Beneath the flow add the muted note “Homebrew and the Brewfile install tools”. Keep every label spelled exactly and legible within the four-band layout.
```
### Configured project groups and prompt cadence

- **File:** `docs/images/ecosystem-schedule.webp`
- **Companion:** [`ecosystem-schedule.prompt.txt`](ecosystem-schedule.prompt.txt)




```text
Use case: infographic-diagram. Asset type: documentation diagram for llm-dependabot's configured project-group schedules and prompt cadence. Create a landscape 3:2 editorial infographic with warm paper #faf8f4, ink #201d18, muted ink #5d574c, fine hairlines #e3ded2, teal #14584d, a Fraunces-like serif title, clear Hanken-like sans labels, and generous whitespace. Use aligned rows and fine dividers. Draw all group icons, including recognisable Python and R marks, as flat, single-colour teal outline icons with matching stroke weight. No shadows, gradients, texture, 3D, cards, emoji, decorative footer, or invented facts. British English.

Title “Configured project groups and prompt cadence”
Subtitle “Each group starts weekly; prompts run when due”

Show five weekday-ordered rows:
- “Web Applications”, note “TypeScript · JavaScript · Astro · Svelte · Vue · HTML · CSS”, schedule “Monday · 11:00”, cadence “update-deps weekly · simplify-codebase and gsc-analysis monthly”. Teal browser/code icon.
- “Python”, note “Python”, schedule “Tuesday · 11:00”, cadence “update-deps weekly · simplify-codebase and gsc-analysis monthly”. Recognisable Python mark as a teal outline icon.
- “Sundry”, note “Unmatched project types”, schedule “Wednesday · 11:00”, cadence “update-deps weekly · simplify-codebase and gsc-analysis monthly”. Teal mixed-collection/toolkit icon.
- “R Packages”, note “R projects”, schedule “Thursday · 11:00”, cadence “all prompts monthly”. Recognisable R mark as a teal outline icon.
- “Pull-request cleanup”, note “Removes worktrees and local branches after PRs merge or close”. Teal pruning shears, visually distinct from the Sundry icon. Do not state a cleanup interval.

Keep all rows aligned, labels legible, exact wording, and logos accurate.
```

**Edit prompt:** Preserve every title, subtitle, word, row, position, size, divider, icon, schedule, cadence, spacing, and colour exactly as shown. Make only one kind of change: restyle the Python and R language marks in their rows so they follow the same flat, single-colour teal outline icon treatment as the browser, toolkit, and pruning-shears icons. Keep each mark recognisable through its familiar silhouette, but draw both as clean teal (`#14584d`) outlines with no official blue/yellow fills, gradients, or shadows. Match the existing icon stroke weight and scale, centred in the same icon column. Do not alter any text or other elements.
### One schedule, multiple prompts

- **File:** `docs/images/multiple-prompts.webp`
- **Companion:** [`multiple-prompts.prompt.txt`](multiple-prompts.prompt.txt)




```text
Use case: infographic-diagram. Asset type: documentation diagram for llm-dependabot's per-prompt run pattern. Create a landscape 3:2 editorial infographic with warm paper #faf8f4, ink #201d18, muted ink #5d574c, fine hairlines #e3ded2, sparse teal #14584d, a Fraunces-like serif title and section labels, Hanken-like sans labels, flat outline icons, and generous whitespace. Use thin left-to-right arrows and no cards, shadows, gradients, texture, 3D, emoji, decorative footer, ordinal numbering, or invented facts. British English.

Title exactly “One schedule, multiple prompts”
Subtitle exactly “Each due prompt gets its own isolated run”
Context line “At each weekly group run, process prompts present in the repository when due”
Muted note “One prompt at a time”

Show four spacious horizontal rows separated by fine hairlines. Every row has its own worktree, agent run, and pull request:
- “update-deps” (note “Weekly”) → “Own Git worktree + branch” → “Coding agent runs this prompt” → “Its own pull request”
- “simplify-codebase” (note “Monthly, when due”) → same flow
- “gsc-analysis” (note “Monthly, when due”) → same flow
- “…” (note “Other configured prompts”) → same flow

Use document icons for prompt labels, distinct worktree/branch icons, agent/terminal icons, and pull-request branch icons. Make clear every due prompt repeats the flow in sequence; do not imply parallel runs. Preserve the literal ellipsis. Ensure all labels are exact and legible at documentation width.
```
### Setup checklist

- **File:** `docs/images/setup-checklist.webp`
- **Companion:** [`setup-checklist.prompt.txt`](setup-checklist.prompt.txt)


```text
Use case: infographic-diagram. Asset type: documentation illustration for llm-dependabot setup. Create a landscape 3:2 editorial checklist matching the warm-paper visual style, refined typography, fine dividers, precise thin outline icons, and generous whitespace. Use background #faf8f4, ink #201d18, muted ink #5d574c, hairlines #e3ded2, and sparse teal #14584d for icons and the arrow. Use Fraunces-like serif headings and Hanken-like sans labels. No cards, panels, shadows, gradients, texture, 3D, emoji, decorative footer, ordinal numbers, invented facts, or private repository names. Title exactly “Make the template yours”. British English.

Show four evenly spaced horizontal bands, divided by hairlines. Each has a large outline icon and serif heading at left, then exact checklist rows with empty square checkboxes:
- “Local setup”: “Clone folder”, “Coding agent”, “Groups & schedule”. Use folder, terminal, and calendar symbols.
- “Choose repositories”: “Public · commit prompts” and “Private · git-ignored private.yaml”. Use a correct small GitHub mark or a generic repository outline, plus globe and lock symbols to distinguish public and private.
- “Standardise prompts”: “.github/prompts/<name>.md” and “Same path in config.yaml”. Use document and linked file/config symbols.
- “Prepare each project”: “AGENTS.md”, “Toolchain & checks”, “Protect default branch”. Use guide, wrench, and shield symbols.

At the bottom, connect a compact terminal icon and the exact label “make setup” with a thin teal downward arrow. Leave the icon and label unboxed and centred beneath the arrow. Keep all wording, filenames, checkboxes, and spelling exact and legible.
```
