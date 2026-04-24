from sqlalchemy.orm import Session

from task_manager.models.task import Priority, Status, Task


def get_all(db: Session) -> list[Task]:
    return db.query(Task).order_by(Task.created_at.desc()).all()


def get_by_id(db: Session, task_id: int) -> Task | None:
    return db.get(Task, task_id)


def create(
    db: Session,
    title: str,
    description: str | None = None,
    priority: Priority = Priority.medium,
) -> Task:
    task = Task(title=title, description=description, priority=priority)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def update(
    db: Session,
    task_id: int,
    title: str | None = None,
    description: str | None = None,
    status: Status | None = None,
    priority: Priority | None = None,
) -> Task | None:
    task = get_by_id(db, task_id)
    if not task:
        return None
    if title is not None:
        task.title = title
    if description is not None:
        task.description = description
    if status is not None:
        task.status = status
    if priority is not None:
        task.priority = priority
    db.commit()
    db.refresh(task)
    return task


def delete(db: Session, task_id: int) -> bool:
    task = get_by_id(db, task_id)
    if not task:
        return False
    db.delete(task)
    db.commit()
    return True
