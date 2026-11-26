# Common operations for llm-dependabot. Run `make help` for the list.

# The CLI, run from this checkout's locked environment.
CLI := uv run --locked --no-dev llm-dependabot
ACTIONS_LOCK_VERSION := v0.5.1
LOG_DIR := $(HOME)/Library/Logs/llm-dependabot
DAYS ?= 30

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

.DEFAULT_GOAL := help
.PHONY: help setup self-update update-deps install uninstall list status dashboard cleanup clean-logs run dry-run lint format format-check typecheck typecoverage test mutation-test deadcode audit build check hooks hooks-install actions-lock-install actions-lock actions-lock-verify check-actions-lock-version docs docs-serve

##@ General

help: ## Show this help
	@awk 'BEGIN {FS = ":.*## "; printf "\n\033[1mUsage:\033[0m make \033[36m<target>\033[0m\n"} \
		/^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } \
		/^[a-zA-Z_-]+:.*## / { printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2 } \
		END { printf "\n" }' $(MAKEFILE_LIST)

##@ Setup

setup: ## Interactive first-time setup (Brewfile, sign-ins, private repos, hooks, launchd, Full Disk Access)
	@command -v brew >/dev/null || { echo "Install Homebrew first: https://brew.sh"; exit 1; }
	@brew bundle check --no-upgrade >/dev/null || { \
		brew bundle check --no-upgrade --verbose || true; \
		printf "Install the missing Brewfile packages? [Y/n] "; read answer; \
		case "$$answer" in [nN]*) exit 1;; esac; \
		brew bundle install --no-upgrade; \
	}
	$(CLI) setup
	@$(MAKE) --no-print-directory actions-lock-install

self-update: ## Pull merged changes into this checkout, then reinstall the app and agents
	@test "$$(git branch --show-current)" = main || { echo "Check out main first: git switch main"; exit 1; }
	@git diff --quiet HEAD || { echo "Commit or stash local changes first"; exit 1; }
	git pull --ff-only --quiet
	@brew bundle check --no-upgrade >/dev/null || brew bundle install --no-upgrade
	$(CLI) install

update-deps: ## Upgrade the locked dependencies, the hook script's lock, and the prek hook revisions
	uv lock --upgrade
	uv lock --upgrade --script hooks/check_private_names.py
	uv sync --locked
	prek update

##@ Schedule

install: ## Build the app, then write and load the launchd agents
	$(CLI) install

uninstall: ## Unload and remove the launchd agents
	$(CLI) uninstall

##@ Runs

list: ## Show which repositories fall into which group
	$(CLI) list

status: ## Show the schedule and pending pull requests
	$(CLI) status

dashboard: ## Build an HTML dashboard of past runs and their pull requests, and open it
	$(CLI) dashboard

cleanup: ## Clean up after merged or closed pull requests
	$(CLI) cleanup

clean-logs: ## Delete run logs older than DAYS days (default 30): make clean-logs [DAYS=7]
	@if [ -d "$(LOG_DIR)" ]; then \
		find "$(LOG_DIR)" -mindepth 1 -mtime +$(DAYS) -delete -print; \
	else \
		echo "No logs in $(LOG_DIR)"; \
	fi

run: ## Run a group's due prompts now: make run GROUP=python [REPO=name] [PROMPT=name]
	@test -n "$(GROUP)" || { echo "usage: make run GROUP=<group> [REPO=<name>] [PROMPT=<name>]"; exit 2; }
	$(CLI) run $(GROUP) $(if $(REPO),--repo $(REPO)) $(if $(PROMPT),--prompt $(PROMPT))

dry-run: ## List what a group would run: make dry-run GROUP=python [PROMPT=name]
	@test -n "$(GROUP)" || { echo "usage: make dry-run GROUP=<group> [PROMPT=<name>]"; exit 2; }
	$(CLI) run $(GROUP) --dry-run $(if $(PROMPT),--prompt $(PROMPT))

##@ Development

lint: ## Lint with ruff
	uv run --locked ruff check

# Twice: formatting can split a line into a multi-line call, which then needs
# its own trailing comma.
format: ## Add missing trailing commas, then format with ruff
	uv run --locked ruff check --select missing-trailing-comma --fix --quiet
	uv run --locked ruff format --quiet
	uv run --locked ruff check --select missing-trailing-comma --fix --quiet
	uv run --locked ruff format

format-check: ## Check formatting with ruff
	uv run --locked ruff format --check

typecheck: ## Type-check with ty against the project's environment
	uv run --locked ty check

typecoverage: ## Require complete strict type coverage with pyrefly
	uv run --locked pyrefly coverage check --fail-under 100 --strict

test: ## Run the pytest suite, requiring full line and branch coverage
	uv run --locked coverage run -m pytest
	uv run --locked coverage report

# mutmut lists every mutant it did not kill; each must be killed, so the
# target shows their diffs and fails while any remain.
mutation-test: ## Mutate the source with mutmut, failing unless the tests kill every mutant
	rm -rf mutants
	uv run --locked mutmut run
	@survivors=$$(uv run --locked mutmut results | cut -d: -f1); \
	if [[ -n "$$survivors" ]]; then \
		for mutant in $$survivors; do uv run --locked mutmut show "$$mutant"; done; \
		echo "$$(wc -w <<< "$$survivors" | tr -d ' ') mutant(s) not killed; see docs/development.md#mutation-testing" >&2; \
		exit 1; \
	fi; \
	echo "The tests killed every mutant"

deadcode: ## Find unused code with unref
	uv run --locked unref

audit: ## Check dependencies for known vulnerabilities (uv audit) and declarations (deptry)
	uv audit --preview-features audit-command --script hooks/check_private_names.py
	uv audit --preview-features audit-command --locked
	uv run --locked deptry src

build: ## Build the package's sdist and wheel into dist/
	uv build --clear

check: lint format-check typecheck typecoverage test deadcode audit build ## Run all development checks and build the package

hooks: ## Run every prek hook on all files
	prek run --all-files

hooks-install: ## Install the prek git hooks (pre-commit and commit-msg)
	prek install

actions-lock-install: ## Install the pinned gh-actions-lock extension the actions.lock hook needs
	@if [[ "$$(gh actions-lock --version 2>/dev/null)" == "actions-lock version $(ACTIONS_LOCK_VERSION)" ]]; then \
		echo "gh-actions-lock $(ACTIONS_LOCK_VERSION) is installed"; \
	else \
		gh extension remove actions-lock >/dev/null 2>&1 || true; \
		gh extension install github/gh-actions-lock --pin $(ACTIONS_LOCK_VERSION); \
	fi

check-actions-lock-version:
	@version=$$(gh actions-lock --version 2>/dev/null) || { \
		echo "Install gh-actions-lock $(ACTIONS_LOCK_VERSION) with: make actions-lock-install" >&2; \
		exit 1; \
	}; \
	if [[ "$$version" != "actions-lock version $(ACTIONS_LOCK_VERSION)" ]]; then \
		echo "Expected actions-lock $(ACTIONS_LOCK_VERSION), found $$version." >&2; \
		exit 1; \
	fi

actions-lock: check-actions-lock-version ## Regenerate .github/workflows/actions.lock, keeping full-SHA refs
	gh actions-lock --no-interactive --no-narrow
	gh actions-lock --verify

actions-lock-verify: check-actions-lock-version ## Check that actions.lock matches every workflow's actions
	gh actions-lock --verify

##@ Documentation

docs: ## Build the documentation site into site/, failing on any warning
	uv run --locked --group docs zensical build --strict --clean

docs-serve: ## Preview the documentation site at http://localhost:8000
	uv run --locked --group docs zensical serve --open
