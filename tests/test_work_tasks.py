"""Business-hours task tests — timer-logic-scaffold pattern.

Covers:
  • business_hours_seconds accumulator (core logic)
  • State machine: all valid transitions and all invalid transitions
  • get_elapsed: running, paused, stopped, idle
  • Boundary conditions required by the skill:
      - Segment starting before 09:00 (only post-09:00 portion counts)
      - Segment ending after 18:00 (only pre-18:00 portion counts)
      - Entirely outside business hours → 0 s
      - Pause spanning midnight (09:00 window handled via absolute datetime)
      - Multi-day span accumulates each day's window independently
      - Resume after restart (timer_started_at persisted; elapsed reconstructed)
  • API endpoints (CRUD + timer) via TestClient
"""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from task_manager.api.main import app
from task_manager.db.database import get_db
from task_manager.models.task import Base, TimerStatus
from task_manager.services import work_task_service as svc

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

MON_9AM = datetime(2024, 1, 15, 9, 0, 0)   # Monday 09:00 — start of work window
MON_6PM = datetime(2024, 1, 15, 18, 0, 0)  # Monday 18:00 — end of work window
TUE_9AM = datetime(2024, 1, 16, 9, 0, 0)
TUE_6PM = datetime(2024, 1, 16, 18, 0, 0)


def _make_engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


@pytest.fixture()
def db() -> Session:
    engine = _make_engine()
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture()
def task(db: Session):
    return svc.create(db, title="BH task")


@pytest.fixture()
def client():
    engine = _make_engine()
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)

    def override():
        s = TestingSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# business_hours_seconds — accumulator unit tests
# ---------------------------------------------------------------------------


def test_bhs_full_day() -> None:
    """A segment spanning exactly the work window yields 9 hours."""
    assert svc.business_hours_seconds(MON_9AM, MON_6PM) == 9 * 3600.0


def test_bhs_entirely_before_window() -> None:
    start = datetime(2024, 1, 15, 6, 0)
    end = datetime(2024, 1, 15, 8, 30)
    assert svc.business_hours_seconds(start, end) == 0.0


def test_bhs_entirely_after_window() -> None:
    start = datetime(2024, 1, 15, 18, 0)
    end = datetime(2024, 1, 15, 22, 0)
    assert svc.business_hours_seconds(start, end) == 0.0


def test_bhs_partial_start_before_window() -> None:
    """Segment starts at 07:00, ends at 11:00 — only 09:00–11:00 counts (2 h)."""
    start = datetime(2024, 1, 15, 7, 0)
    end = datetime(2024, 1, 15, 11, 0)
    assert svc.business_hours_seconds(start, end) == 2 * 3600.0


def test_bhs_partial_end_after_window() -> None:
    """Segment starts at 16:00, ends at 20:00 — only 16:00–18:00 counts (2 h)."""
    start = datetime(2024, 1, 15, 16, 0)
    end = datetime(2024, 1, 15, 20, 0)
    assert svc.business_hours_seconds(start, end) == 2 * 3600.0


def test_bhs_entirely_inside_window() -> None:
    start = datetime(2024, 1, 15, 10, 0)
    end = datetime(2024, 1, 15, 12, 30)
    assert svc.business_hours_seconds(start, end) == 2.5 * 3600.0


def test_bhs_multi_day() -> None:
    """Two consecutive full working days → 2 × 9 h."""
    assert svc.business_hours_seconds(MON_9AM, TUE_6PM) == 2 * 9 * 3600.0


def test_bhs_overnight_segment() -> None:
    """Running from 17:00 Mon to 11:00 Tue: 1 h Mon + 2 h Tue = 3 h."""
    start = datetime(2024, 1, 15, 17, 0)
    end = datetime(2024, 1, 16, 11, 0)
    assert svc.business_hours_seconds(start, end) == 3 * 3600.0


def test_bhs_spanning_midnight_counts_nothing_at_night() -> None:
    """From 22:00 Mon to 07:00 Tue — entirely outside both day's windows."""
    start = datetime(2024, 1, 15, 22, 0)
    end = datetime(2024, 1, 16, 7, 0)
    assert svc.business_hours_seconds(start, end) == 0.0


def test_bhs_zero_length() -> None:
    assert svc.business_hours_seconds(MON_9AM, MON_9AM) == 0.0


def test_bhs_reversed_returns_zero() -> None:
    assert svc.business_hours_seconds(MON_6PM, MON_9AM) == 0.0


# ---------------------------------------------------------------------------
# State machine — happy paths
# ---------------------------------------------------------------------------


def test_start(db: Session, task) -> None:
    t = svc.start_timer(db, task.id, at=MON_9AM)
    assert t.timer_status == TimerStatus.running
    assert t.timer_started_at == MON_9AM
    assert t.elapsed_seconds == 0


def test_pause_accumulates_only_business_hours(db: Session, task) -> None:
    """Pausing after a full working day stores 9 h = 32 400 s."""
    svc.start_timer(db, task.id, at=MON_9AM)
    t = svc.pause_timer(db, task.id, at=MON_6PM)
    assert t.timer_status == TimerStatus.paused
    assert t.elapsed_seconds == 32400
    assert t.timer_started_at is None


def test_resume_and_stop(db: Session, task) -> None:
    svc.start_timer(db, task.id, at=MON_9AM)
    svc.pause_timer(db, task.id, at=datetime(2024, 1, 15, 12, 0))   # 3 h
    svc.resume_timer(db, task.id, at=datetime(2024, 1, 15, 14, 0))
    t = svc.stop_timer(db, task.id, at=datetime(2024, 1, 15, 16, 0))  # +2 h
    assert t.timer_status == TimerStatus.stopped
    assert t.elapsed_seconds == 5 * 3600  # 3 h + 2 h


def test_stop_while_paused(db: Session, task) -> None:
    """Stopping from paused must not double-count the already-committed segment."""
    svc.start_timer(db, task.id, at=MON_9AM)
    svc.pause_timer(db, task.id, at=datetime(2024, 1, 15, 11, 0))   # 2 h
    t = svc.stop_timer(db, task.id, at=datetime(2024, 1, 15, 23, 0))  # well after 18:00
    assert t.elapsed_seconds == 2 * 3600
    assert t.timer_status == TimerStatus.stopped


def test_multiple_cycles(db: Session, task) -> None:
    svc.start_timer(db, task.id, at=MON_9AM)
    svc.pause_timer(db, task.id, at=datetime(2024, 1, 15, 10, 0))   # 1 h
    svc.resume_timer(db, task.id, at=datetime(2024, 1, 15, 11, 0))
    svc.pause_timer(db, task.id, at=datetime(2024, 1, 15, 13, 0))   # 2 h
    svc.resume_timer(db, task.id, at=datetime(2024, 1, 15, 14, 0))
    t = svc.stop_timer(db, task.id, at=datetime(2024, 1, 15, 15, 0))  # 1 h
    assert t.elapsed_seconds == 4 * 3600  # 1 + 2 + 1


# ---------------------------------------------------------------------------
# get_elapsed
# ---------------------------------------------------------------------------


def test_elapsed_idle(db: Session, task) -> None:
    assert svc.get_elapsed(task) == 0.0


def test_elapsed_while_running_counts_only_biz_hours(db: Session, task) -> None:
    svc.start_timer(db, task.id, at=datetime(2024, 1, 15, 8, 0))  # started 1 h before window
    db.refresh(task)
    # At 10:00: only 09:00–10:00 (1 h) should count, not the pre-window hour
    elapsed = svc.get_elapsed(task, at=datetime(2024, 1, 15, 10, 0))
    assert elapsed == 1 * 3600.0


def test_elapsed_paused_does_not_advance(db: Session, task) -> None:
    svc.start_timer(db, task.id, at=MON_9AM)
    svc.pause_timer(db, task.id, at=datetime(2024, 1, 15, 11, 0))  # 2 h committed
    db.refresh(task)
    assert svc.get_elapsed(task, at=datetime(2024, 1, 15, 17, 0)) == 2 * 3600.0
    assert svc.get_elapsed(task, at=TUE_6PM) == 2 * 3600.0  # still frozen


# ---------------------------------------------------------------------------
# Boundary conditions (skill requirements)
# ---------------------------------------------------------------------------


def test_pause_at_end_of_day_then_resume_next_morning(db: Session, task) -> None:
    """Leaving the timer running through the night adds nothing for off-hours."""
    svc.start_timer(db, task.id, at=datetime(2024, 1, 15, 16, 0))  # 16:00 Mon
    # 'Pause' at 08:00 Tue — only 16:00–18:00 Mon (2 h) should count
    t = svc.pause_timer(db, task.id, at=datetime(2024, 1, 16, 8, 0))
    assert t.elapsed_seconds == 2 * 3600


def test_running_overnight_elapsed_correct(db: Session, task) -> None:
    """Timer left running from 17:00 to 10:00 next day: only 1 h + 1 h = 2 h."""
    svc.start_timer(db, task.id, at=datetime(2024, 1, 15, 17, 0))
    db.refresh(task)
    elapsed = svc.get_elapsed(task, at=datetime(2024, 1, 16, 10, 0))
    assert elapsed == 2 * 3600.0  # 1 h Mon evening + 1 h Tue morning


def test_resume_after_restart(db: Session, task) -> None:
    """timer_started_at is persisted; elapsed reconstructed after expire/refresh."""
    svc.start_timer(db, task.id, at=MON_9AM)
    db.expire_all()
    db.refresh(task)
    assert task.timer_status == TimerStatus.running
    assert task.timer_started_at == MON_9AM
    elapsed = svc.get_elapsed(task, at=MON_6PM)
    assert elapsed == 9 * 3600.0


# ---------------------------------------------------------------------------
# Invalid transitions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("transition,setup", [
    ("start",  lambda db, tid: svc.start_timer(db, tid, at=MON_9AM)),
    ("start",  lambda db, tid: (svc.start_timer(db, tid, at=MON_9AM),
                                 svc.stop_timer(db, tid, at=MON_6PM))),
])
def test_cannot_start_when_not_idle(db: Session, task, transition, setup) -> None:
    setup(db, task.id)
    with pytest.raises(ValueError, match="Cannot start"):
        svc.start_timer(db, task.id)


def test_cannot_pause_when_idle(db: Session, task) -> None:
    with pytest.raises(ValueError, match="Cannot pause"):
        svc.pause_timer(db, task.id)


def test_cannot_resume_when_idle(db: Session, task) -> None:
    with pytest.raises(ValueError, match="Cannot resume"):
        svc.resume_timer(db, task.id)


def test_cannot_stop_when_idle(db: Session, task) -> None:
    with pytest.raises(ValueError, match="Cannot stop"):
        svc.stop_timer(db, task.id)


def test_not_found(db: Session) -> None:
    with pytest.raises(ValueError, match="not found"):
        svc.start_timer(db, 9999)


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


def test_api_create_and_list(client) -> None:
    r = client.post("/work-tasks/", json={"title": "API task"})
    assert r.status_code == 201
    assert r.json()["title"] == "API task"
    assert r.json()["timer_status"] == "idle"

    r = client.get("/work-tasks/")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_api_get_not_found(client) -> None:
    assert client.get("/work-tasks/999").status_code == 404


def test_api_delete(client) -> None:
    tid = client.post("/work-tasks/", json={"title": "Del"}).json()["id"]
    assert client.delete(f"/work-tasks/{tid}").status_code == 204
    assert client.get(f"/work-tasks/{tid}").status_code == 404


def test_api_timer_lifecycle(client) -> None:
    tid = client.post("/work-tasks/", json={"title": "Timer task"}).json()["id"]

    r = client.post(f"/work-tasks/{tid}/timer/start")
    assert r.status_code == 200
    assert r.json()["timer_status"] == "running"

    r = client.post(f"/work-tasks/{tid}/timer/pause")
    assert r.status_code == 200
    assert r.json()["timer_status"] == "paused"

    r = client.post(f"/work-tasks/{tid}/timer/resume")
    assert r.status_code == 200
    assert r.json()["timer_status"] == "running"

    r = client.post(f"/work-tasks/{tid}/timer/stop")
    assert r.status_code == 200
    assert r.json()["timer_status"] == "stopped"


def test_api_timer_conflict(client) -> None:
    tid = client.post("/work-tasks/", json={"title": "Conflict"}).json()["id"]
    client.post(f"/work-tasks/{tid}/timer/start")
    r = client.post(f"/work-tasks/{tid}/timer/start")
    assert r.status_code == 409


def test_api_get_timer(client) -> None:
    tid = client.post("/work-tasks/", json={"title": "Get timer"}).json()["id"]
    r = client.get(f"/work-tasks/{tid}/timer")
    assert r.status_code == 200
    assert r.json()["timer_status"] == "idle"
    assert r.json()["elapsed_seconds"] == 0.0
