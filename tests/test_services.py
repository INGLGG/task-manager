import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from task_manager.models.task import Base, Priority, Status
from task_manager.services import task_service, work_task_service


@pytest.fixture()
def db() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


def test_create_task(db: Session) -> None:
    task = task_service.create(db, title="Buy milk")
    assert task.id is not None
    assert task.title == "Buy milk"
    assert task.status == Status.todo
    assert task.task_type == "regular"


def test_get_all(db: Session) -> None:
    task_service.create(db, title="Task A")
    task_service.create(db, title="Task B")
    tasks = task_service.get_all(db)
    assert len(tasks) == 2


def test_get_all_returns_work_tasks_too(db: Session) -> None:
    """task_service.get_all is polymorphic — returns all subtypes."""
    task_service.create(db, title="Regular")
    work_task_service.create(db, title="Work")
    tasks = task_service.get_all(db)
    assert len(tasks) == 2
    types = {t.task_type for t in tasks}
    assert types == {"regular", "work"}


def test_update_status(db: Session) -> None:
    task = task_service.create(db, title="To update")
    updated = task_service.update(db, task.id, status=Status.done)
    assert updated is not None
    assert updated.status == Status.done


def test_delete_task(db: Session) -> None:
    task = task_service.create(db, title="To delete")
    result = task_service.delete(db, task.id)
    assert result is True
    assert task_service.get_by_id(db, task.id) is None


def test_delete_nonexistent(db: Session) -> None:
    assert task_service.delete(db, 999) is False
