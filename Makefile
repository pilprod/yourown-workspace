AGENT ?= all
PYTHON ?= python3

.PHONY: prepare context-check check test verify-pins
prepare:
	bash scripts/prepare-workspace.sh --agent "$(AGENT)"

context-check:
	bash scripts/prepare-workspace.sh --agent "$(AGENT)" --check

check: test context-check
	git diff --check
	git diff --cached --check

test:
	bash -n scripts/prepare-workspace.sh
	$(PYTHON) -B -m unittest discover -s tests -p 'test_*.py' -v

verify-pins:
	bash scripts/prepare-workspace.sh --agent "$(AGENT)" --check --strict
