from datetime import datetime

from sqlalchemy.orm import Session

from task_manager.models.task import Task, TimerStatus
from task_manager.services import task_service

# ---------------------------------------------------------------------------
# Valid transitions
#   idle ──start──► running ──pause──► paused
#                    ▲                    │
#                    └──────resume────────┘
#   running ──stop──► stopped
#   paused  ──stop──► stopped
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.utcnow()


def _fetch(db: Session, task_id: int) -> Task:
    from task_manager.models.work_task import WorkTask  # local import avoids circular dep

    task = task_service.get_by_id(db, task_id)
    if task is None:
        raise ValueError(f"Task {task_id} not found")
    if isinstance(task, WorkTask):
        raise ValueError(
            f"Task {task_id} is a work task — use the /work-tasks timer endpoints"
        )
    return task


def get_elapsed(task: Task, at: datetime | None = None) -> float:
    """Elapsed seconds — delegates to the polymorphic model method.

    Regular Task uses wall-clock math; WorkTask uses business-hours math.
    """
    return task.get_elapsed(at)


def start_timer(db: Session, task_id: int, at: datetime | None = None) -> Task:
    """idle → running."""
    task = _fetch(db, task_id)
    if task.timer_status != TimerStatus.idle:
        raise ValueError(f"Cannot start: timer is already {task.timer_status.value}")
    task.timer_status = TimerStatus.running
    task.timer_started_at = at if at is not None else _now()
    db.commit()
    db.refresh(task)
    return task


def pause_timer(db: Session, task_id: int, at: datetime | None = None) -> Task:
    """running → paused.  Accumulates elapsed seconds for the completed segment."""
    task = _fetch(db, task_id)
    if task.timer_status != TimerStatus.running:
        raise ValueError(f"Cannot pause: timer is {task.timer_status.value}")
    now = at if at is not None else _now()
    assert task.timer_started_at is not None  # invariant: always set when running
    task.elapsed_seconds += int((now - task.timer_started_at).total_seconds())
    task.timer_started_at = None
    task.timer_status = TimerStatus.paused
    db.commit()
    db.refresh(task)
    return task


def resume_timer(db: Session, task_id: int, at: datetime | None = None) -> Task:
    """paused → running.  Records the new segment start time."""
    task = _fetch(db, task_id)
    if task.timer_status != TimerStatus.paused:
        raise ValueError(f"Cannot resume: timer is {task.timer_status.value}")
    task.timer_started_at = at if at is not None else _now()
    task.timer_status = TimerStatus.running
    db.commit()
    db.refresh(task)
    return task


def stop_timer(db: Session, task_id: int, at: datetime | None = None) -> Task:
    """running | paused → stopped.  Finalises elapsed_seconds."""
    task = _fetch(db, task_id)
    if task.timer_status not in (TimerStatus.running, TimerStatus.paused):
        raise ValueError(f"Cannot stop: timer is {task.timer_status.value}")
    if task.timer_status == TimerStatus.running and task.timer_started_at is not None:
        now = at if at is not None else _now()
        task.elapsed_seconds += int((now - task.timer_started_at).total_seconds())
        task.timer_started_at = None
    task.timer_status = TimerStatus.stopped
    db.commit()
    db.refresh(task)
    return task
