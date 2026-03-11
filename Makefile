.PHONY: install test lint clean run

VENV       := .venv
PYTHON     := $(VENV)/bin/python
PIP        := $(VENV)/bin/pip
PYTEST     := $(VENV)/bin/pytest

# Detect uv for faster installs
UV := $(shell command -v uv 2>/dev/null)

# ── Install ──────────────────────────────────────────────
install: $(VENV)/bin/activate
ifdef UV
	$(UV) pip install --python $(PYTHON) ".[test]"
else
	$(PIP) install --upgrade pip
	$(PIP) install ".[test]"
endif
	@echo "\n✓ install complete – run 'make test' to verify"

$(VENV)/bin/activate:
ifdef UV
	$(UV) venv $(VENV) --python python3.11
else
	python3 -m venv $(VENV)
endif

# ── Test ─────────────────────────────────────────────────
test: install
	$(PYTEST) -v --tb=short
	@echo "\n✓ all tests passed"

# ── Lint ─────────────────────────────────────────────────
lint: install
	$(PYTHON) -m ruff check src/ tests/

# ── Run ──────────────────────────────────────────────────
run: install
	$(PYTHON) -m teams_mcp.main

# ── Clean ────────────────────────────────────────────────
clean:
	rm -rf $(VENV) __pycache__ .pytest_cache src/*.egg-info
