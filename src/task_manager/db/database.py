from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from task_manager.config import settings
from task_manager.models.task import Base
import task_manager.models.work_task  # noqa: F401 — registers WorkTask table with Base

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},  # only needed for SQLite
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
