from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from task_manager.models.task import Base, TimerStatus


class WorkTask(Base):
    """Task whose timer only counts seconds inside the 09:00–18:00 window each day.
    Time outside that window is implicitly paused."""

    __tablename__ = "work_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    timer_status: Mapped[TimerStatus] = mapped_column(
        Enum(TimerStatus), default=TimerStatus.idle
    )
    # Persisted so elapsed can be reconstructed after a process restart.
    timer_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    elapsed_seconds: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __init__(self, title: str, description: str | None = None) -> None:
        super().__init__(
            title=title,
            description=description,
            timer_status=TimerStatus.idle,
            elapsed_seconds=0,
        )
