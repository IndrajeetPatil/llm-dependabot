# Common operations for update-deps-scheduler. Run `make help` for the list.

SCRIPT := ./update_deps.py

.DEFAULT_GOAL := help
.PHONY: help install uninstall list status cleanup run dry-run lint format format-check typecheck check

help: ## Show this help
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-14s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Write and load the launchd agents
	$(SCRIPT) install

uninstall: ## Unload and remove the launchd agents
	$(SCRIPT) uninstall

list: ## Show which repositories fall into which group
	$(SCRIPT) list

status: ## Show the schedule and pending pull requests
	$(SCRIPT) status

cleanup: ## Clean up after merged or closed pull requests
	$(SCRIPT) cleanup

run: ## Run a group now: make run GROUP=python [REPO=name]
	@test -n "$(GROUP)" || { echo "usage: make run GROUP=<group> [REPO=<name>]"; exit 2; }
	$(SCRIPT) run $(GROUP) $(if $(REPO),--repo $(REPO))

dry-run: ## List a group's repositories: make dry-run GROUP=python
	@test -n "$(GROUP)" || { echo "usage: make dry-run GROUP=<group>"; exit 2; }
	$(SCRIPT) run $(GROUP) --dry-run

lint: ## Lint with ruff
	uvx ruff check

format: ## Format with ruff
	uvx ruff format

format-check: ## Check formatting with ruff
	uvx ruff format --check

typecheck: ## Type-check with ty
	uvx ty check

check: lint format-check typecheck ## Run all development checks
