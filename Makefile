.PHONY: install test lint

install:
	pip install -e ".[test]"

test:
	python3 -m pytest -v

lint:
	python3 -m ruff check src/ tests/
