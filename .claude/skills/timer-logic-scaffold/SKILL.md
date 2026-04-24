---
name: timer-logic-scaffold
description: When creating or modifying task entities, generate the start/stop/pause/resume timer state machine, accumulator function, and unit tests for boundary conditions (pause at midnight, resume after restart, etc.).
---

## Overview

This skill defines the standard pattern for adding timer functionality to any task entity in this project. It covers three concerns:

1. **State machine** — the four valid timer states and the transitions between them.
2. **Accumulator** — how elapsed time is persisted across pauses and process restarts.
3. **Polymorphic elapsed** — how different task types (regular vs. business-hours) override elapsed-time calculation while sharing the same state machine.

Follow this pattern whenever a new task entity needs a timer. Do not invent a different approach.

---

## 1. State machine

```
idle ──start──► running ──pause──► paused
                  ▲                   │
                  └──────resume───────┘
running ──stop──► stopped
paused  ──stop──► stopped
```

Every task model carries three timer columns:

| Column | Type | Purpose |
|---|---|---|
| `timer_status` | `Enum(TimerStatus)` | Current state: `idle / running / paused / stopped` |
| `timer_started_at` | `DateTime` (nullable) | Wall-clock instant when the current running segment began |
| `elapsed_seconds` | `Integer` | Cumulative seconds from all **completed** segments |

```python
# src/task_manager/models/task.py (excerpt)
class TimerStatus(str, enum.Enum):
    idle    = "idle"
    running = "running"
    paused  = "paused"
    stopped = "stopped"

class Task(Base):
    timer_status:     Mapped[TimerStatus]      = mapped_column(Enum(TimerStatus))
    timer_started_at: Mapped[datetime | None]  = mapped_column(DateTime, nullable=True)
    elapsed_seconds:  Mapped[int]              = mapped_column(Integer, default=0)
```

### Service-layer transitions

Each transition is one function in the service. All functions accept an optional `at: datetime` parameter so tests can inject a deterministic timestamp instead of relying on `datetime.utcnow()`.

```python
# src/task_manager/services/timer_service.py (excerpt)

def start_timer(db: Session, task_id: int, at: datetime | None = None) -> Task:
    task = _fetch(db, task_id)
    if task.timer_status != TimerStatus.idle:
        raise ValueError(f"Cannot start: timer is already {task.timer_status.value}")
    task.timer_status     = TimerStatus.running
    task.timer_started_at = at or datetime.utcnow()
    db.commit(); db.refresh(task)
    return task

def pause_timer(db: Session, task_id: int, at: datetime | None = None) -> Task:
    task = _fetch(db, task_id)
    if task.timer_status != TimerStatus.running:
        raise ValueError(f"Cannot pause: timer is {task.timer_status.value}")
    now = at or datetime.utcnow()
    task.elapsed_seconds  += int((now - task.timer_started_at).total_seconds())
    task.timer_started_at  = None
    task.timer_status      = TimerStatus.paused
    db.commit(); db.refresh(task)
    return task

def resume_timer(db: Session, task_id: int, at: datetime | None = None) -> Task:
    task = _fetch(db, task_id)
    if task.timer_status != TimerStatus.paused:
        raise ValueError(f"Cannot resume: timer is {task.timer_status.value}")
    task.timer_started_at = at or datetime.utcnow()
    task.timer_status     = TimerStatus.running
    db.commit(); db.refresh(task)
    return task

def stop_timer(db: Session, task_id: int, at: datetime | None = None) -> Task:
    task = _fetch(db, task_id)
    if task.timer_status not in (TimerStatus.running, TimerStatus.paused):
        raise ValueError(f"Cannot stop: timer is {task.timer_status.value}")
    if task.timer_status == TimerStatus.running:
        now = at or datetime.utcnow()
        task.elapsed_seconds += int((now - task.timer_started_at).total_seconds())
        task.timer_started_at = None
    task.timer_status = TimerStatus.stopped
    db.commit(); db.refresh(task)
    return task
```

---

## 2. Accumulator — surviving pauses and restarts

`elapsed_seconds` stores only **completed** segments. The live total is computed on demand:

```
total = elapsed_seconds + (now - timer_started_at)   # while running
total = elapsed_seconds                               # while paused or stopped
```

Because `timer_started_at` is persisted to the database, a process restart cannot lose the running segment — the elapsed time is reconstructed from the stored timestamp on the next read.

The accumulator lives as a method on the model so the calculation is co-located with the data:

```python
# src/task_manager/models/task.py
def get_elapsed(self, at: datetime | None = None) -> float:
    base = float(self.elapsed_seconds)
    if self.timer_status == TimerStatus.running and self.timer_started_at is not None:
        reference = at if at is not None else datetime.utcnow()
        base += (reference - self.timer_started_at).total_seconds()
    return base
```

---

## 3. Polymorphic elapsed — business-hours variant

`WorkTask` inherits `Task` but overrides `get_elapsed()` to count only seconds that fall inside the `[09:00, 18:00)` window on each calendar day. The state machine transitions are **identical** — only the elapsed calculation differs.

```python
# src/task_manager/models/work_task.py

WORK_START_HOUR = 9
WORK_END_HOUR   = 18

def business_hours_seconds(start: datetime, end: datetime) -> float:
    """Intersect [start, end) with the daily work window on every spanned day."""
    if end <= start:
        return 0.0
    total, day = 0.0, start.date()
    while day <= end.date():
        w_start = datetime(day.year, day.month, day.day, WORK_START_HOUR)
        w_end   = datetime(day.year, day.month, day.day, WORK_END_HOUR)
        seg_s, seg_e = max(start, w_start), min(end, w_end)
        if seg_e > seg_s:
            total += (seg_e - seg_s).total_seconds()
        day += timedelta(days=1)
    return total

class WorkTask(Task):
    __mapper_args__ = {"polymorphic_identity": "work"}

    def get_elapsed(self, at: datetime | None = None) -> float:
        base = float(self.elapsed_seconds)
        if self.timer_status == TimerStatus.running and self.timer_started_at is not None:
            reference = at if at is not None else datetime.utcnow()
            base += business_hours_seconds(self.timer_started_at, reference)
        return base
```

Callers (CLI, API) always call `task.get_elapsed()` — the correct variant dispatches automatically.

---

## 4. Required boundary-condition tests

Every timer implementation must cover the following cases. Use the `at=` parameter to make all timestamps deterministic.

```python
# tests/test_timer.py — regular task examples

T0 = datetime(2024, 1, 15, 10, 0, 0)

def test_pause_spanning_midnight(db, task):
    """Absolute datetime arithmetic handles midnight rollovers."""
    timer_service.start_timer(db, task.id, at=datetime(2024, 1, 15, 23, 55))
    t = timer_service.pause_timer(db, task.id, at=datetime(2024, 1, 16, 0, 5))
    assert t.elapsed_seconds == 600  # 10 minutes

def test_resume_after_restart(db, task):
    """timer_started_at is persisted; elapsed reconstructed after expire/refresh."""
    timer_service.start_timer(db, task.id, at=T0)
    db.expire_all(); db.refresh(task)           # simulate process restart
    assert task.timer_status == TimerStatus.running
    assert task.timer_started_at == T0
    assert timer_service.get_elapsed(task, at=T0 + timedelta(hours=1)) == 3600.0

def test_elapsed_paused_does_not_advance(db, task):
    """Elapsed must not grow after pausing."""
    timer_service.start_timer(db, task.id, at=T0)
    timer_service.pause_timer(db, task.id,  at=T0 + timedelta(seconds=60))
    db.refresh(task)
    assert timer_service.get_elapsed(task, at=T0 + timedelta(seconds=9999)) == 60.0

def test_stop_while_paused_no_double_count(db, task):
    """Stop from paused state must not add the already-committed segment again."""
    timer_service.start_timer(db, task.id, at=T0)
    timer_service.pause_timer(db, task.id,  at=T0 + timedelta(seconds=120))
    t = timer_service.stop_timer(db, task.id, at=T0 + timedelta(seconds=999))
    assert t.elapsed_seconds == 120


# tests/test_work_tasks.py — business-hours specific

MON_9AM = datetime(2024, 1, 15, 9, 0)
MON_6PM = datetime(2024, 1, 15, 18, 0)

def test_overnight_run_adds_nothing_for_off_hours(db, task):
    """Timer left running from 16:00 to 08:00 next day counts only 2 h."""
    svc.start_timer(db, task.id, at=datetime(2024, 1, 15, 16, 0))
    t = svc.pause_timer(db, task.id, at=datetime(2024, 1, 16, 8, 0))
    assert t.elapsed_seconds == 2 * 3600

def test_segment_entirely_outside_window(db, task):
    assert business_hours_seconds(
        datetime(2024, 1, 15, 22, 0),
        datetime(2024, 1, 16,  7, 0),
    ) == 0.0

def test_multi_day_span(db, task):
    """Two full working days → 2 × 9 h."""
    assert business_hours_seconds(MON_9AM, datetime(2024, 1, 16, 18, 0)) == 2 * 9 * 3600
```

### Minimum test checklist

- [ ] `start` sets `timer_status=running` and `timer_started_at`
- [ ] `pause` accumulates elapsed and clears `timer_started_at`
- [ ] `resume → stop` adds the second segment correctly
- [ ] `stop` from paused does not double-count
- [ ] Multiple pause/resume cycles accumulate correctly
- [ ] `get_elapsed` is frozen after `pause`
- [ ] Midnight rollover handled correctly
- [ ] All 8+ invalid transitions raise `ValueError` with a clear message
- [ ] Post-restart: `expire_all` + `refresh` still reconstructs elapsed
- [ ] *(business-hours only)* Segment before window → 0 s
- [ ] *(business-hours only)* Segment after window → 0 s
- [ ] *(business-hours only)* Overnight run → counts only in-window portions
- [ ] *(business-hours only)* Multi-day span accumulates each day's window

---

## 5. When to apply this skill

Apply this skill whenever a task request says any of:

- "add timer to …"
- "track time on …"
- "start / pause / resume / stop …"
- "count only working hours …"
- "elapsed time for …"
