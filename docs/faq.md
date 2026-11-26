# FAQ

## Why run locally rather than in the cloud?

Your own machine already has everything a maintenance run needs:

- **Credentials stay where they are.** The agent, `gh`, and `git` reuse the
  sign-ins in your keychain, so no token or API key is stored in CI or with a
  hosted service, and a leaked workflow secret cannot push to every
  repository you own.

- **Every toolchain is already set up.** The R, Python, Node.js, and Rust
  installations you develop with are the ones the agent tests with; a cloud
  sandbox needs a setup script, and often a network allowlist, per ecosystem.

- **Your existing plan pays for it.** Agents sign in with the subscription you
  already use interactively, rather than metered API keys, and there are no
  runner minutes to buy.

- **Private code goes nowhere new.** It travels only between GitHub, your
  machine, and the agent's provider, as it does when you work by hand.

The cost is that runs need the machine to be on; see
[when jobs run](usage.md#when-jobs-run) for what happens when it is asleep or
shut down.

## Why not use an agent product's scheduled tasks?

Several coding agents can run a prompt on a schedule in their own cloud, and
for a single repository and a single agent they work well. llm-dependabot
targets a different shape of problem: a whole portfolio of repositories.

- **No lock-in to one provider.** The agent is one `command` line in
  `config.yaml`. When one provider's usage runs out, or a better agent
  appears, switch to another without touching any repository.

- **The prompts live in the repositories.** Each prompt is a committed,
  reviewed file that any agent can run, not text kept in one vendor's
  settings. Changing how a repository is maintained is a pull request.

- **Onboarding is a commit, not a setup step.** A new repository takes part
  as soon as it commits a prompt; there is no task, environment, or
  integration to create for it.

- **One schedule for everything.** Groups stagger the work across the week,
  monthly prompts catch up after a missed run, and worktrees and clones are
  cleaned up once their pull requests close, across every repository at once.

## Why only macOS?

It is a personal tool first: it automates maintenance of my own public and
private repositories, on the only machine I develop on. Supporting other
systems would add code that I could not use or test.

The macOS-specific parts are few and isolated (`launchd`, the Full Disk
Access app, `caffeinate`, notifications, and Homebrew); everything else is
plain `git`, `gh`, and Python. To run elsewhere, fork the template and replace
those parts, as described in
[another operating system](configuration.md#another-operating-system). The
same approach also works on an always-on server or a cloud machine, if you
accept the trade-offs above.

## Which coding agent can I use?

Any agent with a non-interactive mode. Antigravity CLI is the default, and
[the coding agent](configuration.md#the-coding-agent) lists the commands for
Claude Code, Codex CLI, and GitHub Copilot CLI. Nothing else in llm-dependabot
or in the prompts depends on which agent runs them.

## Does it work with GitLab, Bitbucket, or GitHub Enterprise?

It is built for GitHub because that is where my open-source work lives, under
a personal account, so only that setup is used and tested.

- **GitHub Enterprise** should be the smallest step. Every call goes through
  `gh`, which supports Enterprise Server hosts (`gh auth login --hostname`,
  `GH_HOST`), and `owner` can name an organisation as well as a user. Only the
  dashboard's links assume `github.com`.

- **GitLab and Bitbucket** would need a fork. The scheduling, worktrees, and
  agent runs are plain `git` and carry over, but listing repositories,
  checking for prompts, and tracking and labelling pull requests are `gh`
  calls in `github.py`, which would need rewriting against `glab` or the
  Bitbucket API. The prompts themselves would also need to open merge
  requests with that platform's tooling instead of `gh`.

## Is it safe to let an agent run unattended?

The agent runs with your credentials and without asking for approval, so
llm-dependabot limits what it can affect rather than what it can do:

- Every prompt runs in its own worktree and branch, so your clones and
  uncommitted work are never touched.

- Changes arrive only as pull requests. Protect each repository's default
  branch so that holds even if the agent tries to push directly (see
  [protect the default branch](setup.md#protect-the-default-branch)).

- Each repository's checks and an independent review gate every pull request
  before you merge it (see [what a repository needs](autonomy.md#what-a-repository-needs)).

## Does it replace Dependabot or Renovate?

It can. An `update-deps` prompt bumps versions as those bots do, then fixes
the breakage an upgrade causes and adopts what the new versions offer; this
repository maintains its own dependencies that way. You can also keep the
bots for version bumps and use prompts for everything they cannot do.
