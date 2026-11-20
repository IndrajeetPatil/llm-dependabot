# Common operations for llm-dependabot. Run `make help` for the list.

SCRIPT := ./llm_dependabot.py
LOG_DIR := $(HOME)/Library/Logs/llm-dependabot
DAYS ?= 30

.DEFAULT_GOAL := help
.PHONY: help setup update-deps install uninstall list status cleanup clean-logs run dry-run lint format format-check typecheck audit check hooks hooks-install docs docs-serve

##@ General

help: ## Show this help
	@awk 'BEGIN {FS = ":.*## "; printf "\n\033[1mUsage:\033[0m make \033[36m<target>\033[0m\n"} \
		/^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } \
		/^[a-zA-Z_-]+:.*## / { printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2 } \
		END { printf "\n" }' $(MAKEFILE_LIST)

##@ Setup

setup: ## Interactive first-time setup (Brewfile, sign-ins, private repos, hooks, launchd, Full Disk Access)
	@command -v brew >/dev/null || { echo "Install Homebrew first: https://brew.sh"; exit 1; }
	@brew bundle check --no-upgrade >/dev/null || { \
		brew bundle check --no-upgrade --verbose; \
		printf "Install the missing Brewfile packages? [Y/n] "; read answer; \
		case "$$answer" in [nN]*) exit 1;; esac; \
		brew bundle install --no-upgrade; \
	}
	$(SCRIPT) setup

update-deps: ## Upgrade the locked script and docs dependencies and the prek hook revisions
	uv lock --script $(SCRIPT) --upgrade
	uv lock --upgrade
	prek update --freeze

##@ Schedule

install: ## Build the app, then write and load the launchd agents
	$(SCRIPT) install

uninstall: ## Unload and remove the launchd agents
	$(SCRIPT) uninstall

##@ Runs

list: ## Show which repositories fall into which group
	$(SCRIPT) list

status: ## Show the schedule and pending pull requests
	$(SCRIPT) status

cleanup: ## Clean up after merged or closed pull requests
	$(SCRIPT) cleanup

clean-logs: ## Delete run logs older than DAYS days (default 30): make clean-logs [DAYS=7]
	@if [ -d "$(LOG_DIR)" ]; then \
		find "$(LOG_DIR)" -mindepth 1 -mtime +$(DAYS) -delete -print; \
	else \
		echo "No logs in $(LOG_DIR)"; \
	fi

run: ## Run a group's due prompts now: make run GROUP=python [REPO=name] [PROMPT=name]
	@test -n "$(GROUP)" || { echo "usage: make run GROUP=<group> [REPO=<name>] [PROMPT=<name>]"; exit 2; }
	$(SCRIPT) run $(GROUP) $(if $(REPO),--repo $(REPO)) $(if $(PROMPT),--prompt $(PROMPT))

dry-run: ## List what a group would run: make dry-run GROUP=python [PROMPT=name]
	@test -n "$(GROUP)" || { echo "usage: make dry-run GROUP=<group> [PROMPT=<name>]"; exit 2; }
	$(SCRIPT) run $(GROUP) --dry-run $(if $(PROMPT),--prompt $(PROMPT))

##@ Development

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
	uv audit --preview-features audit-command --locked

check: lint format-check typecheck audit ## Run all development checks

hooks: ## Run every prek hook on all files
	prek run --all-files

hooks-install: ## Install the prek git hooks (pre-commit and commit-msg)
	prek install

##@ Documentation

docs: ## Build the documentation site into site/, failing on any warning
	uv run --locked zensical build --strict --clean

docs-serve: ## Preview the documentation site at http://localhost:8000
	uv run --locked zensical serve --open
