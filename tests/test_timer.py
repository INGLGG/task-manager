"""Timer state-machine tests.

Covers all valid/invalid transitions and the boundary conditions called out in
the acceptance criteria: paused sessions, midnight rollovers, and post-restart
reads where timer_started_at is reloaded from the database.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from task_manager.models.task import Base, TimerStatus
from task_manager.services import task_service, timer_service

T0 = datetime(2024, 1, 15, 10, 0, 0)


@pytest.fixture()
def db() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture()
def task(db: Session):
    return task_service.create(db, title="Timed task")


# ---------------------------------------------------------------------------
# Happy-path transitions
# ---------------------------------------------------------------------------


def test_start(db: Session, task) -> None:
    t = timer_service.start_timer(db, task.id, at=T0)
    assert t.timer_status == TimerStatus.running
    assert t.timer_started_at == T0
    assert t.elapsed_seconds == 0


def test_pause_accumulates_elapsed(db: Session, task) -> None:
    timer_service.start_timer(db, task.id, at=T0)
    t = timer_service.pause_timer(db, task.id, at=T0 + timedelta(minutes=5))
    assert t.timer_status == TimerStatus.paused
    assert t.elapsed_seconds == 300
    assert t.timer_started_at is None


def test_resume_then_stop(db: Session, task) -> None:
    timer_service.start_timer(db, task.id, at=T0)
    timer_service.pause_timer(db, task.id, at=T0 + timedelta(minutes=5))
    timer_service.resume_timer(db, task.id, at=T0 + timedelta(minutes=10))
    t = timer_service.stop_timer(db, task.id, at=T0 + timedelta(minutes=13))
    assert t.timer_status == TimerStatus.stopped
    # 5 min running + 3 min running = 480 s
    assert t.elapsed_seconds == 480


def test_stop_while_paused(db: Session, task) -> None:
    """Stopping from paused state must not double-count the paused segment."""
    timer_service.start_timer(db, task.id, at=T0)
    timer_service.pause_timer(db, task.id, at=T0 + timedelta(seconds=120))
    t = timer_service.stop_timer(db, task.id, at=T0 + timedelta(seconds=999))
    assert t.timer_status == TimerStatus.stopped
    assert t.elapsed_seconds == 120  # pause already committed 120 s; stop adds 0


def test_multiple_pause_resume_cycles(db: Session, task) -> None:
    timer_service.start_timer(db, task.id, at=T0)
    timer_service.pause_timer(db, task.id, at=T0 + timedelta(seconds=100))   # +100
    timer_service.resume_timer(db, task.id, at=T0 + timedelta(seconds=200))
    timer_service.pause_timer(db, task.id, at=T0 + timedelta(seconds=250))   # +50
    timer_service.resume_timer(db, task.id, at=T0 + timedelta(seconds=300))
    t = timer_service.stop_timer(db, task.id, at=T0 + timedelta(seconds=400))  # +100
    assert t.elapsed_seconds == 250  # 100 + 50 + 100


# ---------------------------------------------------------------------------
# get_elapsed — accumulator function
# ---------------------------------------------------------------------------


def test_elapsed_idle(db: Session, task) -> None:
    assert timer_service.get_elapsed(task) == 0.0


def test_elapsed_while_running(db: Session, task) -> None:
    timer_service.start_timer(db, task.id, at=T0)
    db.refresh(task)
    elapsed = timer_service.get_elapsed(task, at=T0 + timedelta(seconds=90))
    assert elapsed == 90.0


def test_elapsed_while_paused_does_not_advance(db: Session, task) -> None:
    """After pausing, elapsed must not grow even if time keeps passing."""
    timer_service.start_timer(db, task.id, at=T0)
    timer_service.pause_timer(db, task.id, at=T0 + timedelta(seconds=60))
    db.refresh(task)
    elapsed_at_pause = timer_service.get_elapsed(task, at=T0 + timedelta(seconds=60))
    elapsed_long_after = timer_service.get_elapsed(task, at=T0 + timedelta(seconds=9999))
    assert elapsed_at_pause == 60.0
    assert elapsed_long_after == 60.0  # frozen


# ---------------------------------------------------------------------------
# Boundary conditions
# ---------------------------------------------------------------------------


def test_pause_spanning_midnight(db: Session, task) -> None:
    """Absolute datetime arithmetic handles midnight rollovers without special logic."""
    start = datetime(2024, 1, 15, 23, 55, 0)
    pause_at = datetime(2024, 1, 16, 0, 5, 0)  # 10 minutes later, past midnight
    timer_service.start_timer(db, task.id, at=start)
    t = timer_service.pause_timer(db, task.id, at=pause_at)
    assert t.elapsed_seconds == 600


def test_resume_after_restart(db: Session, task) -> None:
    """timer_started_at is persisted so elapsed can be computed after a process restart."""
    start = datetime(2024, 1, 15, 9, 0, 0)
    timer_service.start_timer(db, task.id, at=start)

    # Simulate app restart: expire all in-memory state and reload from DB.
    db.expire_all()
    db.refresh(task)

    assert task.timer_status == TimerStatus.running
    assert task.timer_started_at == start  # survived the "restart"

    elapsed = timer_service.get_elapsed(task, at=start + timedelta(hours=1))
    assert elapsed == 3600.0


# ---------------------------------------------------------------------------
# Invalid transitions
# ---------------------------------------------------------------------------


def test_cannot_start_when_running(db: Session, task) -> None:
    timer_service.start_timer(db, task.id, at=T0)
    with pytest.raises(ValueError, match="Cannot start"):
        timer_service.start_timer(db, task.id, at=T0)


def test_cannot_start_when_stopped(db: Session, task) -> None:
    timer_service.start_timer(db, task.id, at=T0)
    timer_service.stop_timer(db, task.id, at=T0 + timedelta(seconds=1))
    with pytest.raises(ValueError, match="Cannot start"):
        timer_service.start_timer(db, task.id)


def test_cannot_pause_when_idle(db: Session, task) -> None:
    with pytest.raises(ValueError, match="Cannot pause"):
        timer_service.pause_timer(db, task.id)


def test_cannot_pause_when_paused(db: Session, task) -> None:
    timer_service.start_timer(db, task.id, at=T0)
    timer_service.pause_timer(db, task.id, at=T0 + timedelta(seconds=10))
    with pytest.raises(ValueError, match="Cannot pause"):
        timer_service.pause_timer(db, task.id)


def test_cannot_resume_when_idle(db: Session, task) -> None:
    with pytest.raises(ValueError, match="Cannot resume"):
        timer_service.resume_timer(db, task.id)


def test_cannot_resume_when_running(db: Session, task) -> None:
    timer_service.start_timer(db, task.id, at=T0)
    with pytest.raises(ValueError, match="Cannot resume"):
        timer_service.resume_timer(db, task.id)


def test_cannot_stop_when_idle(db: Session, task) -> None:
    with pytest.raises(ValueError, match="Cannot stop"):
        timer_service.stop_timer(db, task.id)


def test_cannot_stop_when_stopped(db: Session, task) -> None:
    timer_service.start_timer(db, task.id, at=T0)
    timer_service.stop_timer(db, task.id, at=T0 + timedelta(seconds=1))
    with pytest.raises(ValueError, match="Cannot stop"):
        timer_service.stop_timer(db, task.id)


def test_not_found_raises_value_error(db: Session) -> None:
    with pytest.raises(ValueError, match="not found"):
        timer_service.start_timer(db, 9999)
