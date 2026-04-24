from datetime import date, datetime, timedelta

from task_manager.models.task import Base, Task, TimerStatus

WORK_START_HOUR: int = 9
WORK_END_HOUR: int = 18


def business_hours_seconds(start: datetime, end: datetime) -> float:
    """Seconds of [start, end) that fall within WORK_START_HOUR–WORK_END_HOUR on each calendar day.

    Handles midnight crossings, multi-day spans, and segments entirely outside
    the window (→ 0 s) without any special-case branching.
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


class WorkTask(Task):
    """Task whose timer counts only seconds inside the 09:00–18:00 window each day.

    Inherits all columns from Task via single-table inheritance. The only
    behavioural difference is get_elapsed(), which intersects each running
    segment with the daily business-hours window.
    """

    __mapper_args__ = {"polymorphic_identity": "work"}

    def __init__(self, title: str, description: str | None = None) -> None:
        # Call Base.__init__ directly so Task.__init__ cannot overwrite task_type
        # with "regular". priority and due_date are not relevant for work tasks.
        from task_manager.models.task import Status
        Base.__init__(
            self,
            title=title,
            description=description,
            task_type="work",
            status=Status.todo,
            timer_status=TimerStatus.idle,
            elapsed_seconds=0,
        )

    def get_elapsed(self, at: datetime | None = None) -> float:
        """Business-hours elapsed seconds, including the live running segment."""
        base = float(self.elapsed_seconds)
        if self.timer_status == TimerStatus.running and self.timer_started_at is not None:
            reference = at if at is not None else datetime.utcnow()
            base += business_hours_seconds(self.timer_started_at, reference)
        return base
