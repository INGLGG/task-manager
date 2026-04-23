# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
cp .env.example .env
make dev-install
```

## Commands

```bash
make run          # start API server at http://localhost:8000 (auto-reloads)
make test         # run all tests
make lint         # ruff check + mypy
make format       # ruff format

pytest tests/test_api.py -v        # run a single test file
pytest -k test_create_task -v      # run a single test by name
```

## Architecture

The app exposes the same business logic through two interfaces — a **FastAPI REST API** and a **Typer CLI** — both talking to a SQLite database via SQLAlchemy.

**Data flow:**
```
HTTP request → api/routes/tasks.py (Pydantic schemas) → services/task_service.py → SQLAlchemy ORM → DB
CLI command  → cli/commands.py                         → services/task_service.py → SQLAlchemy ORM → DB
```

- `models/task.py` — single `Task` ORM model with `Priority` and `Status` enums. `Base` is defined here; all schema creation derives from it.
- `services/task_service.py` — all CRUD logic lives here; takes a `Session` as first arg. Neither API nor CLI layer should contain DB logic.
- `db/database.py` — creates the engine from `settings.database_url`, exposes `get_db()` (FastAPI dependency) and `SessionLocal` (used directly by CLI). `init_db()` runs `Base.metadata.create_all` on startup.
- `config.py` — single `Settings` instance loaded from `.env`. `DATABASE_URL` defaults to `sqlite:///./tasks.db`.
- `api/main.py` — FastAPI app; calls `init_db()` in the lifespan hook; mounts the tasks router under `/tasks`.
- Pydantic schemas (`TaskCreate`, `TaskUpdate`, `TaskResponse`) live in the route file, not in a separate `schemas/` module.

**Tests** use an in-memory SQLite database. API tests override the `get_db` FastAPI dependency; service tests construct a `Session` directly. No mocking of the ORM layer.

## Custom skill

A local skill `timer-logic-scaffold` (`.claude/skills/timer-logic-scaffold/`) is available. Invoke it when creating or modifying task timer functionality — it generates the start/stop/pause/resume state machine, accumulator, and boundary-condition unit tests.
