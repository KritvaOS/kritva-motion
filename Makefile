# kritva-motion: make targets. Standard check targets (kritva-program v2/planning/ACCEPTANCE_STANDARD.md).
# Kritva Makefile standard (kritva-program v2/planning/standards/MAKEFILE_STANDARD.md): `make` or `make help` lists the targets.
# A target is documented by `name: ## text` on its rule line; `##@ Name` starts a help group.
# An unimplemented gate exits 3 (NOT_IMPLEMENTED). It is never a pass.
.DEFAULT_GOAL := help
.PHONY: help

##@ Help
help: ## Show this list
	@awk 'BEGIN { FS = ":.*##"; printf "\nUsage: make <target> [VAR=value ...]\n" } \
	  /^##@/ { g = substr($$0, 5); next } \
	  /^[a-zA-Z0-9_.-]+:[^=].*##/ { if (g != "") { printf "\n%s\n", g; g = "" }; sub(/^ +/, "", $$2); printf "  %-24s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

##@ Checks
.PHONY: check docs-check check-readme

REQUIRED := ACCEPTANCE_CRITERIA.md AGENTS.md CONTRIBUTING.md SECURITY.md LICENSE README.md \
  planning/TASKS.md planning/MILESTONE.md planning/MILESTONE_STATUS.md planning/REVIEW_CHECKLIST.md \
  planning/GIT_COMMIT_STEP.md planning/CHANGELOG.md .github/CODEOWNERS

check: ## Required planning files exist; commit-message checker tests pass
	@for f in $(REQUIRED); do test -f $$f || { echo "missing $$f"; exit 1; }; done
	@python3 -m unittest discover -s tests/commit_message_check
	@echo "check ok"

docs-check: ## Every relative Markdown link points to an existing file
	@python3 scripts/docs_check.py

check-readme: ## Structural check of README.md (metadata, topics, relative links)
	@python3 scripts/check_readme.py README.md

##@ Gates (unimplemented gates exit 3)
.PHONY: lint test-unit test-integration test-regression test acceptance
define not_implemented
	@echo "NOT_IMPLEMENTED: $(1) has no tests yet; this is not a pass"; exit 3
endef

lint: ## Static analysis and lint (NOT_IMPLEMENTED: exits 3)
	$(call not_implemented,lint)
test-unit: ## Unit tests (NOT_IMPLEMENTED: exits 3)
	$(call not_implemented,test-unit)
test-integration: ## Integration tests (NOT_IMPLEMENTED: exits 3)
	$(call not_implemented,test-integration)
test-regression: ## Regression tests (NOT_IMPLEMENTED: exits 3)
	$(call not_implemented,test-regression)
test: ## All tests (NOT_IMPLEMENTED: exits 3)
	$(call not_implemented,test)
acceptance: ## Acceptance gate (NOT_IMPLEMENTED: exits 3)
	$(call not_implemented,acceptance)

##@ Git
.PHONY: git_sync
git_sync: ## Switch to main, fast-forward from origin, prune, delete merged local branches
	@git switch main
	@git pull --ff-only --prune
	@git branch --format='%(refname:short)' | grep -vx main | xargs -r git branch -d
	@git log --oneline -3
