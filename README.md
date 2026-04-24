# Task Manager

A task manager usable as a **REST API** (FastAPI) or **CLI** (Typer).

## Project structure

```
task-manager/
├── src/
│   └── task_manager/
│       ├── models/        # SQLAlchemy ORM models
│       ├── services/      # Business logic (DB-agnostic)
│       ├── api/           # FastAPI app + routes
│       ├── cli/           # Typer CLI commands
│       ├── db/            # Engine, session, migrations
│       └── config.py      # Settings via pydantic-settings
├── tests/
├── scripts/
│   └── seed.py            # Sample data loader
├── .env.example
├── pyproject.toml
└── Makefile
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
cp .env.example .env
make dev-install
```

## Run as API

```bash
make run
# http://localhost:8000/docs
```

## Run as CLI

```bash
task-manager --help
task-manager add "Buy milk" --priority high
task-manager list
task-manager done 1
task-manager delete 1
```

## Tests

```bash
make test
```

## Resetting the database

> **Warning: this permanently deletes all tasks and work tasks. There is no undo.**

The database is a local SQLite file (`tasks.db`). You must reset it manually whenever the schema changes (e.g. after a model migration) or to start from a clean state.

```bash
rm -f tasks.db
```

The file is recreated automatically with the current schema the next time you run the API server or any CLI command.
