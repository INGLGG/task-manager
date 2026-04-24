# Agent Log

Maps each acceptance-criteria item to the code that implements it.

## AC: Timer logic is robust to pauses and resumed sessions

### Design decision — accumulator pattern

`timer_started_at` (a `DateTime` column) is persisted to the database whenever
the timer enters the `running` state.  `elapsed_seconds` (an `Integer` column)
accumulates only the *completed* running segments.  The live total is computed
by `get_elapsed()` as:

```
elapsed_seconds + (now - timer_started_at)   # while running
elapsed_seconds                              # while paused or stopped
```

Because `timer_started_at` is stored in the DB rather than in memory, a process
restart cannot lose a running segment — the elapsed time is reconstructed from
the persisted timestamp on the next read.

### Files changed / created

| File | What was added |
|---|---|
| `src/task_manager/models/task.py` | `TimerStatus` enum; `timer_status`, `timer_started_at`, `elapsed_seconds` columns on `Task`; explicit `__init__` so Python-level defaults are available before any DB flush |
| `src/task_manager/services/timer_service.py` | State machine (`start` / `pause` / `resume` / `stop`) + `get_elapsed` accumulator with optional `at` parameter for deterministic testing |
| `src/task_manager/api/routes/timer.py` | REST endpoints: `GET /tasks/{id}/timer`, `POST …/start`, `…/pause`, `…/resume`, `…/stop` |
| `src/task_manager/api/main.py` | Mounts the timer router under `/tasks/{task_id}/timer` |
| `src/task_manager/cli/commands.py` | `timer` sub-app with `start`, `pause`, `resume`, `stop`, `status` commands |

### Test coverage (all in `tests/test_timer.py`)

| Test | Boundary condition |
|---|---|
| `test_pause_spanning_midnight` | Timer started at 23:55, paused at 00:05 next day → 600 s |
| `test_resume_after_restart` | `db.expire_all()` + `db.refresh()` simulates process restart; `timer_started_at` reloaded from DB, elapsed still correct |
| `test_elapsed_while_paused_does_not_advance` | `get_elapsed` called long after pause — value frozen at pause instant |
| `test_stop_while_paused` | Stop from paused state must not double-count the already-committed segment |
| `test_multiple_pause_resume_cycles` | Three running segments accumulate correctly |
| invalid-transition tests (×8) | Every forbidden state change raises `ValueError` with a clear message |

---

## AC: CI green

### Pre-existing failures fixed

| Test file | Root cause | Fix |
|---|---|---|
| `tests/test_api.py` (5 tests) | `sqlite:///:memory:` opens a new in-memory DB per pool connection; `create_all` ran on connection A, route sessions used connection B (empty DB) | Added `poolclass=StaticPool` so all connections share one DBAPI connection; wrapped fixture with `with TestClient(app) as c:` for proper lifespan teardown |
| `tests/test_models.py::test_task_defaults` | `mapped_column(default=...)` in SQLAlchemy 2.x is an INSERT-time default, not a Python `__init__` default; `Task(title="...")` returned `None` for `status` and `priority` | Added explicit `__init__` to `Task` with Python-level keyword defaults |

Result: **40 / 40 passed**.

---

## AC: Business-hours task — timer counts only 09:00–18:00 each day

**Prompt:** "create the logic on the API and the CLI for a new type of task … tracked under working hours, from 9am till 6pm; time not covered in that window is considered as pause."

**Skill applied:** `timer-logic-scaffold` — state machine + accumulator + boundary-condition tests.

### Design decision — `business_hours_seconds` accumulator

The key difference from a regular task timer is the accumulator function.
Instead of `(end - start).total_seconds()`, elapsed is computed by intersecting
each calendar day's running segment with the `[09:00, 18:00)` window:

```
for each day d in [start.date .. end.date]:
    seg = intersection([start, end], [d 09:00, d 18:00])
    total += seg.duration
```

This handles midnight crossings, multi-day spans, and segments entirely outside
the window (→ 0 s) without any special-case branching.

The `timer_started_at` column is still persisted to the DB, so the live elapsed
can be reconstructed after a process restart using the same formula.

### Files changed / created

| File | What was added |
|---|---|
| `src/task_manager/models/work_task.py` | **New** — `WorkTask` ORM model sharing `Base` and `TimerStatus` from `task.py` |
| `src/task_manager/services/work_task_service.py` | **New** — `business_hours_seconds`, `get_elapsed`, CRUD, and state machine (`start` / `pause` / `resume` / `stop`) with injectable `at` parameter |
| `src/task_manager/api/routes/work_tasks.py` | **New** — `POST/GET /work-tasks/`, `GET/DELETE /work-tasks/{id}`, `GET/POST /work-tasks/{id}/timer/{action}` |
| `src/task_manager/api/main.py` | Mounts `work_tasks` router under `/work-tasks` |
| `src/task_manager/db/database.py` | Imports `work_task` module so `WorkTask` table is registered with `Base` before `create_all` |
| `src/task_manager/cli/commands.py` | `work` sub-app (add / list / show / delete) + nested `work timer` sub-app (start / pause / resume / stop / status) |

### Test coverage (`tests/test_work_tasks.py` — 34 tests)

| Group | Tests |
|---|---|
| `business_hours_seconds` accumulator | full day, before/after window, partial overlap, multi-day, overnight, midnight crossing, zero-length, reversed |
| State machine (happy paths) | start, pause accumulates BH seconds only, resume→stop, stop-while-paused, multiple cycles |
| `get_elapsed` | idle, running (pre-window start trimmed), paused frozen |
| Boundary conditions | overnight run → 0 s off-hours; leave running past 18:00; resume after restart |
| Invalid transitions | pause/resume/stop when idle; double-start; not-found |
| API endpoints | CRUD lifecycle, timer lifecycle, 409 conflict, 404 not-found |

**Total suite: 74 / 74 passed.**

---

## AC: Live API run — create tasks via REST endpoints

**Prompt:** "Run the current API project and hit the corresponding endpoints for creating these tasks: one work task with title 'Testing from Claude Agent', one regular task 'Testing with Agent for searching from CLI'. Track the work and results in AGENT_LOG."

### Steps taken

1. Started the FastAPI server with `make run` (uvicorn, auto-reload, port 8000).
2. Waited for the server to become reachable (`GET /docs` returned 200).
3. Hit the two creation endpoints.

### Requests and responses

**Work task (`POST /work-tasks/`)**

```
Request:  POST http://localhost:8000/work-tasks/
          Content-Type: application/json
          {"title": "Testing from Claude Agent"}

Response: 201 Created
{
    "id": 2,
    "title": "Testing from Claude Agent",
    "description": null,
    "timer_status": "idle",
    "elapsed_seconds": 0,
    "created_at": "2026-04-24T00:05:09.331560",
    "updated_at": "2026-04-24T00:05:09.331564"
}
```

**Regular task (`POST /tasks/`)**

```
Request:  POST http://localhost:8000/tasks/
          Content-Type: application/json
          {"title": "Testing with Agent for searching from CLI"}

Response: 201 Created
{
    "id": 2,
    "title": "Testing with Agent for searching from CLI",
    "description": null,
    "status": "todo",
    "priority": "medium",
    "due_date": null,
    "created_at": "2026-04-24T00:05:13.731830",
    "updated_at": "2026-04-24T00:05:13.731834"
}
```

### Result

Both tasks created successfully. Both return `201 Created` with the full persisted record. The work task shows `timer_status: idle` and `elapsed_seconds: 0` (business-hours accumulator ready to start). The regular task shows `status: todo` and `priority: medium` (default values from `Task.__init__`). The server was stopped after both calls.

---

## AC: WorkTask inherits from Task — single-table inheritance + polymorphism

**Prompt:** "Modify each task entity so both work task and regular task have the same methods and properties. WorkTask will inherit from Task. The only difference is that WorkTask only considers time running between 09:00–18:00. With polymorphism, GET /tasks/ retrieves both types; GET /work-tasks/ retrieves only work tasks. A `task_type` property distinguishes them ('regular'/'work'). In the CLI, `list` shows all tasks; `work list` shows only work tasks."

### Design decision — Single Table Inheritance (STI)

`WorkTask` and `Task` share every column, so a single `tasks` table with a `task_type` discriminator column is the cleanest mapping. SQLAlchemy's STI feature handles class-level routing automatically:

- `db.query(Task)` → returns **all** rows (regular + work tasks as polymorphic instances)
- `db.query(WorkTask)` → adds `WHERE task_type = 'work'` automatically

The only behavioural difference is `get_elapsed()`:
- `Task.get_elapsed()` — wall-clock: `elapsed_seconds + (now - timer_started_at)`
- `WorkTask.get_elapsed()` — business-hours: intersects the running segment with the `[09:00, 18:00)` window per calendar day

All other methods (`start_timer`, `pause_timer`, etc.) are inherited unchanged.

### Files changed

| File | What changed |
|---|---|
| `src/task_manager/models/task.py` | Added `TaskType` enum; added `task_type` discriminator column; `__mapper_args__` with `polymorphic_on="task_type"`, `polymorphic_identity="regular"`; `status`/`priority` made nullable (work tasks carry `None`); added `get_elapsed()` method (wall-clock) |
| `src/task_manager/models/work_task.py` | Rewrote as STI subclass of `Task` — no `__tablename__`, no column definitions; `__mapper_args__ = {"polymorphic_identity": "work"}`; `business_hours_seconds` moved here (pure time logic); `get_elapsed()` overridden with business-hours math; `__init__` calls `Base.__init__` directly to avoid `Task.__init__` overwriting `task_type="regular"` |
| `src/task_manager/services/work_task_service.py` | Imports `business_hours_seconds` from model (re-exported for test backward compat); `get_by_id` changed to `db.query(WorkTask).filter(...)` so discriminator filter is applied; `get_elapsed` is now a thin wrapper over `task.get_elapsed(at)` |
| `src/task_manager/services/timer_service.py` | `get_elapsed` delegates to `task.get_elapsed(at)` (polymorphic dispatch); `_fetch` guard: raises `ValueError` if fetched task is a `WorkTask` (prevents wall-clock timer from being applied to a work task via the wrong endpoint) |
| `src/task_manager/api/routes/tasks.py` | `TaskResponse` gains `task_type`, `timer_status`, `elapsed_seconds`; `status`/`priority` become `Optional` (work tasks serialize them as `null`) |
| `src/task_manager/api/routes/work_tasks.py` | `WorkTaskResponse` gains `task_type` field |
| `src/task_manager/cli/commands.py` | `list` command adds "Type" column and handles `status=None` / `priority=None` for work-task rows; title updated to "All Tasks" |
| `tests/test_models.py` | Added `task_type` assertion to `test_task_defaults`; new `test_work_task_defaults` and `test_work_task_is_task_subclass` |
| `tests/test_services.py` | Added `test_get_all_returns_work_tasks_too` (polymorphic query); added `task_type` assertion to `test_create_task` |
| `tests/test_api.py` | Added `task_type` assertion; two new tests: `test_tasks_list_includes_work_tasks` (mixed list) and `test_work_task_appears_in_tasks_list_with_null_status` |
| `tests/test_work_tasks.py` | Added `test_work_task_type` (verifies inheritance, `task_type="work"`, `status=None`, `priority=None`) |

### Schema note

The `work_tasks` table is gone. All tasks now live in the single `tasks` table. An existing `tasks.db` file must be deleted and recreated (or migrated) before running the live server, since the schema now includes the `task_type` column.

### Test coverage

**Total suite: 80 / 80 passed.**

New tests added:
| Test | What it verifies |
|---|---|
| `test_task_defaults` (updated) | `task_type == "regular"` on regular Task |
| `test_work_task_defaults` | `task_type == "work"`, `status is None`, `priority is None` |
| `test_work_task_is_task_subclass` | `isinstance(WorkTask(), Task)` |
| `test_get_all_returns_work_tasks_too` | Polymorphic `task_service.get_all` includes work tasks |
| `test_tasks_list_includes_work_tasks` | `GET /tasks/` returns both types |
| `test_work_task_in_tasks_list_has_todo_status_and_no_priority` | Work task has `status='todo'` and `priority=None` in unified list |
| `test_work_task_type` | Inheritance chain + discriminator value correct |

---

## AC: Remove due_date, default status todo, add Elapsed to CLI list

**Prompts:**
- "Remove Due Date cause its not needed, same for the CLI"
- "Set the default status as 'todo' for every new task"
- "Add the Elapsed column in the CLI when listing the tasks"
- "Reset the db for having the changes on place"

### Changes

| File | What changed |
|---|---|
| `src/task_manager/models/task.py` | Removed `due_date` column and `__init__` parameter |
| `src/task_manager/models/work_task.py` | `WorkTask.__init__` now passes `status=Status.todo` so all new tasks default to `todo` |
| `src/task_manager/services/task_service.py` | Removed `due_date` from `create` and `update` signatures |
| `src/task_manager/api/routes/tasks.py` | Removed `due_date` from `TaskCreate`, `TaskUpdate`, `TaskResponse` |
| `src/task_manager/cli/commands.py` | Removed `--due` from `add`/`update`; removed Due Date column from `list`/`show`; added **Elapsed** column to `list` via `t.get_elapsed()` (polymorphic — wall-clock for regular, business-hours for work); dropped unused `datetime` import and `DATE_FORMAT` |
| `README.md` | Added "Resetting the database" section with warning |
| `tests/test_api.py`, `tests/test_cli.py`, `tests/test_models.py`, `tests/test_work_tasks.py` | Updated assertions to reflect `status='todo'` on work tasks and removed `due_date` from helpers |

### DB reset

Deleted `tasks.db` so `init_db()` recreates the schema with the new columns on next run.

### CLI bug fix (stale DB)

`task-manager list` was failing with `OperationalError: no such column: tasks.task_type` because the on-disk `tasks.db` had the pre-STI schema. `create_all` never alters existing tables, so the new column was never added. Fixed by deleting the stale file.

**Total suite: 80 / 80 passed.**

---

## AC: Complete skill documentation with overview and examples

**Prompt:** "Complete the 2 skills in the project with an Overview, a little explanation, and when possible with coding examples."

### Changes

| File | What changed |
|---|---|
| `.claude/skills/commits-standards/SKILL.md` | Added full Overview, two-step workflow (log then commit), subject-line rules table, bullet-list body rules, full `git commit` example with HEREDOC, prefix cheat-sheet, and anti-patterns |
| `.claude/skills/timer-logic-scaffold/SKILL.md` | Added full Overview, state machine diagram with column reference table, service-layer transition code examples (`start`/`pause`/`resume`/`stop`), accumulator explanation with formula, polymorphic `get_elapsed` override example for `WorkTask`, boundary-condition test suite with code, minimum test checklist, and trigger phrases |

### Result

Both skills are now self-contained references. A future agent instance reading either file has enough context to apply the pattern without consulting the rest of the codebase.
