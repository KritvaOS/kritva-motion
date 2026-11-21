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
PYTHON ?= python3
define not_implemented
	@echo "NOT_IMPLEMENTED: $(1) has no tests yet; this is not a pass"; exit 3
endef

lint: ## Static analysis and lint (NOT_IMPLEMENTED: exits 3)
	$(call not_implemented,lint)
test-unit: ## Unit tests and conformance manifest gate (PYTHON=... selects the interpreter)
	@$(PYTHON) scripts/test_gate.py
test-integration: ## Integration tests: scenarios through the driver, stores, engine and a backend (PYTHON=... selects the interpreter)
	@$(PYTHON) scripts/integration_gate.py
test-regression: ## Regression gate: golden traces compared byte for byte
	@$(PYTHON) scripts/regression_gate.py
test: ## All tests: unit, integration and regression
	@$(MAKE) --no-print-directory test-unit test-integration test-regression
acceptance: ## Acceptance gate (NOT_IMPLEMENTED: exits 3)
	$(call not_implemented,acceptance)

##@ Preflight
# "make preflight" is the one command to run before pushing. It runs the checks CI runs on a pull request,
# keeps going after a failure, prints a summary, fixes nothing and never fetches or installs anything.
# Not mirrored: secret-scan (gitleaks) and the PR gate's remote rules (required workflows and approvals).
# PREFLIGHT_BASE is the branch the commits are compared with; run "git fetch origin" first.
# The test targets need the pinned test dependencies: pip install -r requirements-test.txt (preflight does not install anything).
.PHONY: preflight preflight-commits readme-test progress-check hooks-install preflight-hook-on preflight-hook-off

PREFLIGHT_BASE ?= origin/main
PREFLIGHT_STEPS := check docs-check check-readme readme-test progress-check preflight-commits test-unit test-integration test-regression

preflight: ## Run the CI checks locally and report every failure (PREFLIGHT_BASE=origin/main)
	@fail=""; \
	for step in $(PREFLIGHT_STEPS); do \
	  echo ""; echo "[preflight] >>> $$step"; \
	  if $(MAKE) --no-print-directory $$step; then :; else fail="$$fail $$step"; fi; \
	done; \
	echo ""; \
	if [ -n "$$fail" ]; then \
	  echo "[preflight] FAILED:$$fail"; \
	  echo "[preflight] Fix these, then run make preflight again. CI would reject this push."; \
	  exit 1; \
	fi; \
	echo "[preflight] All preflight checks passed. CI also runs secret-scan."

preflight-commits: ## Check the commits since PREFLIGHT_BASE: message rules, commit format and the PR gate (static)
	@git rev-parse --verify --quiet "$(PREFLIGHT_BASE)^{commit}" >/dev/null || { echo "[preflight-commits] $(PREFLIGHT_BASE) not found. Run: git fetch origin"; exit 2; }
	@$(PYTHON) scripts/security/check_commit_messages.py --range "$(PREFLIGHT_BASE)..HEAD"
	@$(PYTHON) scripts/security/check_commit_format.py --range "$(PREFLIGHT_BASE)..HEAD"
	@$(PYTHON) scripts/pipeline/pr_gate.py static --gate .github/kritva-gate.json --base "$(PREFLIGHT_BASE)" --head HEAD

readme-test: ## Run the README checker unit tests (same as the readme-check workflow)
	@$(PYTHON) -m unittest discover -s tests/readme_check -v

progress-check: ## Check status/STATUS.md against its pinned program snapshot (same as the progress-check workflow)
	@$(PYTHON) scripts/progress_report.py --check

hooks-install: ## Enable the repository Git hooks (.githooks): make preflight runs before every git push
	git config core.hooksPath .githooks
	@echo "[hooks] core.hooksPath set to .githooks; pre-push runs make preflight."
	@echo "[hooks] Turn it off with: make preflight-hook-off. Skip it once with: git push --no-verify"

preflight-hook-on: ## Run "make preflight" before every git push (the default after hooks-install)
	git config kritva.preflightOnPush true
	@echo "[hooks] pre-push preflight is ON for this clone. It needs core.hooksPath (make hooks-install)."

preflight-hook-off: ## Turn off the pre-push preflight in this clone (CI still runs every check)
	git config kritva.preflightOnPush false
	@echo "[hooks] pre-push preflight is OFF for this clone."

##@ Git
.PHONY: git_sync
git_sync: ## Switch to main, fast-forward from origin, prune, delete merged local branches
	@git switch main
	@git pull --ff-only --prune
	@git branch --format='%(refname:short)' | grep -vx main | xargs -r git branch -d
	@git log --oneline -3
