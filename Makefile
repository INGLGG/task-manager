.PHONY: install dev-install run test lint format

install:
	pip install -e .

dev-install:
	pip install -e ".[dev]"

run:
	uvicorn task_manager.api.main:app --reload

test:
	pytest -v

lint:
	ruff check src tests
	mypy src

format:
	ruff format src tests
