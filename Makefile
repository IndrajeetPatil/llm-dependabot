# Common operations for llm-dependabot. Run `make help` for the list.

SCRIPT := ./llm_dependabot.py

.DEFAULT_GOAL := help
.PHONY: help setup update-deps install uninstall list status cleanup run dry-run lint format format-check typecheck audit check hooks hooks-install

help: ## Show this help
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-14s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Interactive first-time setup (Brewfile, sign-ins, private repos, hooks, launchd, Full Disk Access)
	@command -v brew >/dev/null || { echo "Install Homebrew first: https://brew.sh"; exit 1; }
	@brew bundle check --no-upgrade >/dev/null || { \
		brew bundle check --no-upgrade --verbose; \
		printf "Install the missing Brewfile packages? [Y/n] "; read answer; \
		case "$$answer" in [nN]*) exit 1;; esac; \
		brew bundle install --no-upgrade; \
	}
	$(SCRIPT) setup

update-deps: ## Upgrade the locked script dependencies and the prek hook revisions
	uv lock --script $(SCRIPT) --upgrade
	prek update --freeze

install: ## Build the app, then write and load the launchd agents
	$(SCRIPT) install

uninstall: ## Unload and remove the launchd agents
	$(SCRIPT) uninstall

list: ## Show which repositories fall into which group
	$(SCRIPT) list

status: ## Show the schedule and pending pull requests
	$(SCRIPT) status

cleanup: ## Clean up after merged or closed pull requests
	$(SCRIPT) cleanup

run: ## Run a group's due prompts now: make run GROUP=python [REPO=name] [PROMPT=name]
	@test -n "$(GROUP)" || { echo "usage: make run GROUP=<group> [REPO=<name>] [PROMPT=<name>]"; exit 2; }
	$(SCRIPT) run $(GROUP) $(if $(REPO),--repo $(REPO)) $(if $(PROMPT),--prompt $(PROMPT))

dry-run: ## List what a group would run: make dry-run GROUP=python [PROMPT=name]
	@test -n "$(GROUP)" || { echo "usage: make dry-run GROUP=<group> [PROMPT=<name>]"; exit 2; }
	$(SCRIPT) run $(GROUP) --dry-run $(if $(PROMPT),--prompt $(PROMPT))

lint: ## Lint with ruff
	uvx ruff check

format: ## Format with ruff
	uvx ruff format

format-check: ## Check formatting with ruff
	uvx ruff format --check

typecheck: ## Type-check with ty against the script's environment
	uv sync --script $(SCRIPT) --quiet
	uvx ty check --python "$$(uv python find --script $(SCRIPT))"

audit: ## Check the locked dependencies for known vulnerabilities with uv audit
	uv audit --preview-features audit-command --script $(SCRIPT) --locked
	uv audit --preview-features audit-command --script hooks/check_private_names.py

check: lint format-check typecheck audit ## Run all development checks

hooks: ## Run every prek hook on all files
	prek run --all-files

hooks-install: ## Install the prek git hooks (pre-commit and commit-msg)
	prek install
