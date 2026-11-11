.PHONY: test clean

# The tests need Python 3.10 or later: pytest 9.1.1 (requirements-dev.txt) won't install on older.
# PYTHON=/path/to/python overrides the search below, which takes the first python3.N on PATH
# that's 3.10 or later, then python3 itself.
PYTHON ?= $(shell for p in python3.15 python3.14 python3.13 python3.12 python3.11 python3.10 python3; do \
	command -v $$p >/dev/null 2>&1 && $$p -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null && { echo $$p; break; }; \
	done)

test: .venv/done
	.venv/bin/python -m pytest -q tests

.venv/done: requirements-dev.txt pyproject.toml
	@test -n "$(PYTHON)" || { echo "make: no Python 3.10 or later on PATH; set PYTHON=/path/to/python3.10+" >&2; exit 1; }
	rm -rf .venv
	$(PYTHON) -m venv .venv
	.venv/bin/python -m pip install -q --disable-pip-version-check -r requirements-dev.txt
	.venv/bin/python -m pip install -q --disable-pip-version-check --no-build-isolation -e .
	touch $@

clean:
	rm -rf .venv
