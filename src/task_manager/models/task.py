import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Priority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class Status(str, enum.Enum):
    todo = "todo"
    in_progress = "in_progress"
    done = "done"


class TaskType(str, enum.Enum):
    regular = "regular"
    work = "work"


class TimerStatus(str, enum.Enum):
    idle = "idle"
    running = "running"
    paused = "paused"
    stopped = "stopped"


class Task(Base):
    __tablename__ = "tasks"
    __mapper_args__ = {
        "polymorphic_on": "task_type",
        "polymorphic_identity": "regular",
    }

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Discriminator column — "regular" or "work"
    task_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # Nullable so WorkTask rows carry None for these regular-only fields
    status: Mapped[Status | None] = mapped_column(Enum(Status), nullable=True)
    priority: Mapped[Priority | None] = mapped_column(Enum(Priority), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    timer_status: Mapped[TimerStatus] = mapped_column(Enum(TimerStatus), default=TimerStatus.idle)
    timer_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    elapsed_seconds: Mapped[int] = mapped_column(Integer, default=0)

    def __init__(
        self,
        title: str,
        description: str | None = None,
        status: Status | None = Status.todo,
        priority: Priority | None = Priority.medium,
    ) -> None:
        super().__init__(
            title=title,
            description=description,
            task_type="regular",
            status=status,
            priority=priority,
            timer_status=TimerStatus.idle,
            elapsed_seconds=0,
        )

    def get_elapsed(self, at: datetime | None = None) -> float:
        """Wall-clock elapsed seconds, including the live running segment."""
        base = float(self.elapsed_seconds)
        if self.timer_status == TimerStatus.running and self.timer_started_at is not None:
            reference = at if at is not None else datetime.utcnow()
            base += (reference - self.timer_started_at).total_seconds()
        return base
