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


class TimerStatus(str, enum.Enum):
    idle = "idle"
    running = "running"
    paused = "paused"
    stopped = "stopped"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[Status] = mapped_column(Enum(Status), default=Status.todo)
    priority: Mapped[Priority] = mapped_column(Enum(Priority), default=Priority.medium)
    due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Timer fields — persist running-segment start so elapsed survives restarts
    timer_status: Mapped[TimerStatus] = mapped_column(
        Enum(TimerStatus), default=TimerStatus.idle
    )
    timer_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    elapsed_seconds: Mapped[int] = mapped_column(Integer, default=0)

    def __init__(
        self,
        title: str,
        description: str | None = None,
        status: Status = Status.todo,
        priority: Priority = Priority.medium,
        due_date: datetime | None = None,
    ) -> None:
        # Explicit __init__ so Python-level defaults are set before any DB flush,
        # making attribute access on unsaved instances predictable.
        super().__init__(
            title=title,
            description=description,
            status=status,
            priority=priority,
            due_date=due_date,
            timer_status=TimerStatus.idle,
            elapsed_seconds=0,
        )
