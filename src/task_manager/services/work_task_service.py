"""Business-hours task service.

Timer scaffold (per timer-logic-scaffold skill):
  idle ──start──► running ──pause──► paused
                   ▲                    │
                   └──────resume────────┘
  running ──stop──► stopped
  paused  ──stop──► stopped

Accumulator: only seconds that fall inside WORK_START_HOUR–WORK_END_HOUR each
calendar day are counted.  Anything outside that window is implicitly paused,
so a timer left running overnight or over a weekend accumulates nothing during
the off-hours period.
"""

from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from task_manager.models.task import TimerStatus
from task_manager.models.work_task import WorkTask

WORK_START_HOUR: int = 9
WORK_END_HOUR: int = 18


# ---------------------------------------------------------------------------
# Core accumulator
# ---------------------------------------------------------------------------


def business_hours_seconds(start: datetime, end: datetime) -> float:
    """Return the seconds of the [start, end) interval that fall within
    WORK_START_HOUR–WORK_END_HOUR on each calendar day.

    Works correctly across midnight, multi-day, and multi-week spans.
    Accepts an optional `at` timestamp so callers can compute elapsed at any
    deterministic point in time (required for unit-testing boundary conditions
    such as midnight rollovers and post-restart reads).
    """
    if end <= start:
        return 0.0

    total = 0.0
    day: date = start.date()
    end_date: date = end.date()

    while day <= end_date:
        window_start = datetime(day.year, day.month, day.day, WORK_START_HOUR)
        window_end = datetime(day.year, day.month, day.day, WORK_END_HOUR)
        seg_start = max(start, window_start)
        seg_end = min(end, window_end)
        if seg_end > seg_start:
            total += (seg_end - seg_start).total_seconds()
        day += timedelta(days=1)

    return total


def get_elapsed(task: WorkTask, at: datetime | None = None) -> float:
    """Total business-hours elapsed seconds, including the live running segment."""
    base = float(task.elapsed_seconds)
    if task.timer_status == TimerStatus.running and task.timer_started_at is not None:
        reference = at if at is not None else _now()
        base += business_hours_seconds(task.timer_started_at, reference)
    return base


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def create(db: Session, title: str, description: str | None = None) -> WorkTask:
    task = WorkTask(title=title, description=description)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_all(db: Session) -> list[WorkTask]:
    return db.query(WorkTask).order_by(WorkTask.created_at.desc()).all()


def get_by_id(db: Session, task_id: int) -> WorkTask | None:
    return db.get(WorkTask, task_id)


def delete(db: Session, task_id: int) -> bool:
    task = get_by_id(db, task_id)
    if task is None:
        return False
    db.delete(task)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Timer state machine
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.utcnow()


def _fetch(db: Session, task_id: int) -> WorkTask:
    task = get_by_id(db, task_id)
    if task is None:
        raise ValueError(f"WorkTask {task_id} not found")
    return task


def start_timer(db: Session, task_id: int, at: datetime | None = None) -> WorkTask:
    """idle → running."""
    task = _fetch(db, task_id)
    if task.timer_status != TimerStatus.idle:
        raise ValueError(f"Cannot start: timer is already {task.timer_status.value}")
    task.timer_status = TimerStatus.running
    task.timer_started_at = at if at is not None else _now()
    db.commit()
    db.refresh(task)
    return task


def pause_timer(db: Session, task_id: int, at: datetime | None = None) -> WorkTask:
    """running → paused.  Commits only the business-hours portion of the segment."""
    task = _fetch(db, task_id)
    if task.timer_status != TimerStatus.running:
        raise ValueError(f"Cannot pause: timer is {task.timer_status.value}")
    assert task.timer_started_at is not None
    now = at if at is not None else _now()
    task.elapsed_seconds += int(business_hours_seconds(task.timer_started_at, now))
    task.timer_started_at = None
    task.timer_status = TimerStatus.paused
    db.commit()
    db.refresh(task)
    return task


def resume_timer(db: Session, task_id: int, at: datetime | None = None) -> WorkTask:
    """paused → running."""
    task = _fetch(db, task_id)
    if task.timer_status != TimerStatus.paused:
        raise ValueError(f"Cannot resume: timer is {task.timer_status.value}")
    task.timer_started_at = at if at is not None else _now()
    task.timer_status = TimerStatus.running
    db.commit()
    db.refresh(task)
    return task


def stop_timer(db: Session, task_id: int, at: datetime | None = None) -> WorkTask:
    """running | paused → stopped.  Finalises elapsed_seconds."""
    task = _fetch(db, task_id)
    if task.timer_status not in (TimerStatus.running, TimerStatus.paused):
        raise ValueError(f"Cannot stop: timer is {task.timer_status.value}")
    if task.timer_status == TimerStatus.running and task.timer_started_at is not None:
        now = at if at is not None else _now()
        task.elapsed_seconds += int(business_hours_seconds(task.timer_started_at, now))
        task.timer_started_at = None
    task.timer_status = TimerStatus.stopped
    db.commit()
    db.refresh(task)
    return task
