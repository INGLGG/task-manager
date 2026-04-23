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
