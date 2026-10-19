# kritva-motion: standard check targets (kritva-program v2/planning/ACCEPTANCE_STANDARD.md).
# An unimplemented gate exits 3 (NOT_IMPLEMENTED). It is never a pass.
.PHONY: check lint test-unit test-integration test-regression test docs-check acceptance check-readme

REQUIRED := ACCEPTANCE_CRITERIA.md AGENTS.md CONTRIBUTING.md SECURITY.md LICENSE README.md \
  planning/TASKS.md planning/MILESTONE.md planning/MILESTONE_STATUS.md planning/REVIEW_CHECKLIST.md \
  planning/GIT_COMMIT_STEP.md planning/CHANGELOG.md .github/CODEOWNERS

check:
	@for f in $(REQUIRED); do test -f $$f || { echo "missing $$f"; exit 1; }; done
	@python3 -m unittest discover -s tests/commit_message_check
	@echo "check ok"

define not_implemented
	@echo "NOT_IMPLEMENTED: $(1) has no tests yet; this is not a pass"; exit 3
endef

lint:
	$(call not_implemented,lint)
test-unit:
	$(call not_implemented,test-unit)
test-integration:
	$(call not_implemented,test-integration)
test-regression:
	$(call not_implemented,test-regression)
test:
	$(call not_implemented,test)
docs-check:
	@python3 scripts/docs_check.py
acceptance:
	$(call not_implemented,acceptance)
check-readme:
	@python3 scripts/check_readme.py README.md
