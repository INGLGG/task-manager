"""Business-hours task service.

Timer scaffold (per timer-logic-scaffold skill):
  idle ──start──► running ──pause──► paused
                   ▲                    │
                   └──────resume────────┘
  running ──stop──► stopped
  paused  ──stop──► stopped

Elapsed is computed via business_hours_seconds (09:00–18:00 each calendar day).
Off-hours time is implicitly discarded — the timer need not be manually paused
at end-of-day.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from task_manager.models.task import TimerStatus
from task_manager.models.work_task import WorkTask, business_hours_seconds  # re-exported for tests

__all__ = [
    "business_hours_seconds",
    "create",
    "get_all",
    "get_by_id",
    "delete",
    "get_elapsed",
    "start_timer",
    "pause_timer",
    "resume_timer",
    "stop_timer",
]


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
    # Use query (not db.get) so the discriminator filter is applied automatically.
    return db.query(WorkTask).filter(WorkTask.id == task_id).first()


def delete(db: Session, task_id: int) -> bool:
    task = get_by_id(db, task_id)
    if task is None:
        return False
    db.delete(task)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Elapsed helper — delegates to the polymorphic model method
# ---------------------------------------------------------------------------


def get_elapsed(task: WorkTask, at: datetime | None = None) -> float:
    """Business-hours elapsed seconds (delegates to WorkTask.get_elapsed)."""
    return task.get_elapsed(at)


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
