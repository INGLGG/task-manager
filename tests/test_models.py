from task_manager.models.task import Priority, Status, Task, TimerStatus
from task_manager.models.work_task import WorkTask


def test_task_defaults() -> None:
    task = Task(title="Test task")
    assert task.task_type == "regular"
    assert task.status == Status.todo
    assert task.priority == Priority.medium
    assert task.description is None
    assert task.timer_status == TimerStatus.idle
    assert task.elapsed_seconds == 0
    assert task.timer_started_at is None


def test_work_task_defaults() -> None:
    task = WorkTask(title="Work task")
    assert task.task_type == "work"
    assert task.status == Status.todo
    assert task.priority is None
    assert task.description is None
    assert task.timer_status == TimerStatus.idle
    assert task.elapsed_seconds == 0
    assert task.timer_started_at is None


def test_work_task_is_task_subclass() -> None:
    assert issubclass(WorkTask, Task)
    wt = WorkTask(title="Subclass check")
    assert isinstance(wt, Task)


def test_priority_values() -> None:
    assert Priority.low.value == "low"
    assert Priority.medium.value == "medium"
    assert Priority.high.value == "high"


def test_status_values() -> None:
    assert Status.todo.value == "todo"
    assert Status.in_progress.value == "in_progress"
    assert Status.done.value == "done"
