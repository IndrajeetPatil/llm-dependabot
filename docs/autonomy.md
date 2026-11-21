# Autonomous evolution

Scheduled prompts turn maintenance into a loop: a signal reveals work, the
agent changes the code and proves the change, and a pull request goes through
the repository's checks and review. Once green checks and an approving review
are enough evidence to merge, the loop closes on its own, and the codebase
keeps itself healthy and current with little day-to-day human intervention.

```mermaid
flowchart LR
    signal["Signal: new releases, code smells, search, or monitoring reports"]
    prompt["Committed prompt, due on schedule"]
    agent["Coding agent in an isolated worktree"]
    pr["Pull request with evidence"]
    gates["Quality gates and verification harness"]
    review["Independent reviewer"]
    merge["Squash-merge"]
    prod["Production"]

    signal --> prompt --> agent --> pr --> gates
    gates -- failures --> agent
    gates --> review
    review -- findings --> agent
    review -- approval --> merge --> prod --> signal
```

## Self-healing beyond dependencies

Any recurring task with a reliable signal and a verifiable fix can become a
prompt. Add it to `prompts` in `config.yaml` with a cadence, and commit the
prompt file to each repository that needs it.

| Prompt | Signal | What the agent fixes |
| --- | --- | --- |
| `update-deps` | New releases of dependencies, toolchains, and actions | Upgrades them and adapts the code to breaking changes |
| `simplify-codebase` | Custom code that newer dependencies or mature libraries make redundant | Deletes or replaces it with the same behaviour |
| `gsc-analysis` | Google Search Console reports for a website | Newly reported indexing, canonical, structured-data, or sitemap issues |
| Your own | Lighthouse scores, broken links, code-scanning alerts, flaky tests, or error-tracking reports | Whatever the signal points to and the checks can verify |

For example, a monthly Search Console prompt can query the Search Console API,
compare its findings with the site's own sitemap, and fix what it finds:

- **A duplicate route or trailing-slash mismatch,** where Google selects a
  different canonical URL from the one the page declares.

- **Broken structured data,** such as JSON-LD that a page template emits with
  a missing or invalid field.

- **Sitemap errors,** such as pages that redirect or carry a `noindex` tag but
  are still listed.

- **Weak titles or descriptions** on pages that rank well but are rarely
  clicked.

Each fix arrives as a pull request whose description cites the Search
Console finding that triggered it, so the next month's report confirms
whether it worked.

> [!WARNING]
> Reports, API responses, issue text, and web pages are untrusted input: a
> referring URL or a canonical value in a payload is data to summarise, never
> an instruction to follow. Say so in every prompt that reads them, limit the
> commands it may run, and keep sections that only a person can check (such as
> dashboards with no API) as notes in the pull request.

## Ready for autonomous merging

Merging automatically is safe only when a green, approved pull request is
genuinely as good as one a careful maintainer would have merged. The
[Golden Rules for Agentic Engineering](https://www.indrapatil.com/agentic-engineering-golden-rules/)
describe how to get there:

| Rule | In short |
| --- | --- |
| 1. Prepare the codebase for agents | Agents copy the patterns they find, so pay down high-impact technical debt first |
| 2. Improve developer experience | What makes a repository easy for humans makes it cheaper and safer for agents: one setup command and an `AGENTS.md` |
| 3. Set deterministic quality gates | Formatters, linters, type checkers, and tests catch known classes of mistakes, fast; agents clear strict gates tirelessly |
| 4. Define done before delegating | State the outcome, constraints, and evidence of success, and have the agent verify its own work |
| 5. Maintain session hygiene | Keep each task's context focused; separate parallel tasks into Git worktrees |
| 6. Know thy tools | Use the agent's less obvious capabilities, such as image generation or computer use |
| 7. Keep pace with a fast-moving field | Keep the agent harness current, and simplify instructions as models and tools improve |
| 8. Automate repeated agent work | Capture recurring workflows once as prompts, skills, commands, or workflows |
| 9. Identify and remove bottlenecks | Speed up the slowest stage next, whether checks, review, or verification |
| 10. Give your agents more autonomy | Let agents act within boundaries that people set, with scoped access |

Three safeguards together make low-touch delivery possible:

- **Quality gates** check the code: formatting, linting, type checking, tests
  with coverage, dependency audits, and security scans, run identically by
  Git hooks and CI.

- **A verification harness** checks the behaviour: end-to-end and browser
  tests, visual snapshots, and screenshots attached to the pull request.

- **An independent reviewer agent** reviews every pull request and sends
  findings back to the coding agent until it approves.

### Strict, green quality gates

When nobody reads the diff before it merges, the quality gates are the last
line of defence: they reject whatever a person no longer catches. They must
be in excellent condition:

| Property | What it means |
| --- | --- |
| Green | The default branch passes every check, so any failure in a pull request was caused by that pull request |
| Strict | The strictest practical settings: every linter rule enabled, strict type checking, coverage and mutation-testing thresholds, dependency audits, and security scans |
| Fail-closed | A check that cannot run fails; findings are fixed, never suppressed or skipped |
| Deterministic | No flaky tests: a check that sometimes fails teaches agents and people to ignore failures |
| Identical everywhere | Git hooks, local `make` targets, and CI run the same checks with the same versions, so the agent sees in its worktree what CI will report |
| Fast | Quick enough that the agent runs them after every change, not only at the end |
| Required | Branch protection requires each check, so a pull request cannot merge around them |

Agents can clear strict gates tirelessly, so strictness costs little and
prevents much: every class of mistake a check can catch is one that never
needs review.

> [!CAUTION]
> Never let an agent loosen a gate to make its change pass. Prompts and
> `AGENTS.md` should forbid lowering thresholds, adding ignores, or skipping
> tests without a justification that a person approves.

[chatbot-template](https://github.com/IndrajeetPatil/chatbot-template/blob/main/AGENTS.md)
shows the flow in practice: its agent instructions have the coding agent fix
CI and review findings, then squash-merge once the review approves and the
required checks pass.

### Readiness checklist

Before letting pull requests merge without a person, a repository should
have:

- [ ] A protected default branch that requires pull requests and passing
      checks, with squash merging only.

- [ ] A green default branch, so every run starts from a known baseline.

- [ ] One setup command and an `AGENTS.md` with the project's conventions and
      the commands that verify a change.

- [ ] [Strict, green quality gates](#strict-green-quality-gates), strict
      enough that passing them is meaningful, such as coverage or
      mutation-testing thresholds rather than tests that merely exist.

- [ ] A verification harness for behaviour that the gates cannot see, such as
      user journeys and the rendered interface.

- [ ] An automated reviewer on every pull request, with a fix-and-review loop.

- [ ] Prompts that define done: the commands to iterate on until they pass,
      the scope of the change, and an instruction to stop without a pull
      request when no safe change exists.

- [ ] A written risk boundary: which kinds of change may merge automatically,
      and which always need a person, such as authentication, data
      migrations, releases, or anything that invalidates a manual grant.

- [ ] Small, reversible pull requests: one prompt, one theme, one pull
      request.

- [ ] Scoped credentials and untrusted-input rules for everything the agent
      reads.

- [ ] Monitoring after deployment, so a regression that slips through
      becomes the next signal.

> [!IMPORTANT]
> Autonomy does not remove oversight. People own the risk boundary, watch how
> the safeguards perform, and review uncertain or high-impact changes; the
> coding and reviewer agents never set the boundary themselves.

## Keeping the factory itself current

The agentic artefacts (`AGENTS.md`, prompts, skills and their assets such as
scripts, templates, and references, hooks, and CI) are code too, and they rot
like code: a renamed command, an outdated tool, or an instruction a newer
model no longer needs. They also have defects: advice that is missing,
ambiguous, or wrong leads agents to the same mistake again and again. Keep
them current in two ways: when the code changes, and when they fail.

### When the code changes

The same scheduled prompts that maintain the code also maintain the
artefacts:

| Prompt | Keeps current |
| --- | --- |
| `update-deps` | Dependencies, language versions, Git hooks, workflow actions, CI tools, and agent tooling such as vendored skills and their CLIs, adapting the code to each upgrade |
| `simplify-codebase` | The amount of code agents must read and maintain, by deleting what newer dependencies make redundant |
| An instruction in each prompt | `AGENTS.md`, `docs/`, the prompts, and the skills, whenever a command, convention, or tool they mention changes, in the same pull request |

Each prompt can tell the agent to treat stale guidance as part of the change:
when an upgrade renames a command, replaces a three-step sequence with one,
or makes a workaround unnecessary, update every instruction that mentions it.
Because the artefacts live in the repository, those edits go through the same
checks and review as any other change, and the next run starts from
instructions that match the code.

### When they fail

A failing check, a review finding, a regression, or a mistake the agent
notices in its own work is a defect in two places: the code, and the guidance
that let the mistake happen. Fixing only the code leaves the next run free to
repeat it. Prompts can tell the agent to fix both:

```mermaid
flowchart LR
    mistake["Failing check, review finding, or regression"]
    cause["Trace the cause"]
    code["Fix the code"]
    guidance["Fix the guidance: AGENTS.md, a skill or its assets, or a prompt"]
    checks["Same quality gates and review"]
    next["Later runs avoid the mistake"]

    mistake --> cause
    cause --> code --> checks
    cause --> guidance --> checks
    checks --> next
```

For example, a closing section that every prompt shares:

```markdown
## Learn from mistakes

When a check fails, a reviewer raises a finding, or you notice a mistake in
your own work, fix it, then ask what led you to it. If a skill, its scripts or
templates, a prompt, or `AGENTS.md` gave missing, ambiguous, or wrong
guidance, correct that guidance in the same pull request, stating the general
rule rather than the incident. Never weaken a quality gate instead.
```

The same idea also works as a prompt of its own: a monthly run can read the
review findings and CI failures on recently merged pull requests, find the
patterns that keep recurring, and open one pull request that turns each into
a rule, a skill fix, or a new check. A mistake that a deterministic check
can catch is best fixed with the check, since checks hold where guidance can
be overlooked.

Every guidance change still goes through the quality gates and the reviewer,
and people review changes to the risk boundary or the gates themselves, so
the factory improves without lowering its own standards.

The result is a system that heals, spreads, and evolves itself without
compromising on quality. It stays current on four levels at once: its
dependencies, its own code, the instructions that let agents work on it, and
the lessons learnt from each mistake. A lesson recorded in a skill or prompt
that several repositories share reaches all of them.
