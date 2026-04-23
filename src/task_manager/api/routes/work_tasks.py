from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from task_manager.db.database import get_db
from task_manager.models.task import TimerStatus
from task_manager.services import work_task_service

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class WorkTaskCreate(BaseModel):
    title: str
    description: str | None = None


class WorkTaskResponse(BaseModel):
    id: int
    title: str
    description: str | None
    timer_status: TimerStatus
    elapsed_seconds: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkTaskTimerResponse(BaseModel):
    task_id: int
    timer_status: TimerStatus
    elapsed_seconds: float  # business-hours seconds; float for sub-second precision


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _timer_resp(task_id: int, task: object) -> WorkTaskTimerResponse:
    return WorkTaskTimerResponse(
        task_id=task_id,
        timer_status=task.timer_status,  # type: ignore[attr-defined]
        elapsed_seconds=work_task_service.get_elapsed(task),  # type: ignore[arg-type]
    )


def _not_found(task_id: int) -> HTTPException:
    return HTTPException(status_code=404, detail=f"WorkTask {task_id} not found")


def _conflict(msg: str) -> HTTPException:
    return HTTPException(status_code=409, detail=msg)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@router.post("/", response_model=WorkTaskResponse, status_code=status.HTTP_201_CREATED)
def create_work_task(
    payload: WorkTaskCreate, db: Session = Depends(get_db)
) -> object:
    return work_task_service.create(db, **payload.model_dump())


@router.get("/", response_model=list[WorkTaskResponse])
def list_work_tasks(db: Session = Depends(get_db)) -> object:
    return work_task_service.get_all(db)


@router.get("/{task_id}", response_model=WorkTaskResponse)
def get_work_task(task_id: int, db: Session = Depends(get_db)) -> object:
    task = work_task_service.get_by_id(db, task_id)
    if task is None:
        raise _not_found(task_id)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_work_task(task_id: int, db: Session = Depends(get_db)) -> None:
    if not work_task_service.delete(db, task_id):
        raise _not_found(task_id)


# ---------------------------------------------------------------------------
# Timer endpoints
# ---------------------------------------------------------------------------


@router.get("/{task_id}/timer", response_model=WorkTaskTimerResponse)
def get_timer(task_id: int, db: Session = Depends(get_db)) -> WorkTaskTimerResponse:
    task = work_task_service.get_by_id(db, task_id)
    if task is None:
        raise _not_found(task_id)
    return _timer_resp(task_id, task)


@router.post("/{task_id}/timer/start", response_model=WorkTaskTimerResponse)
def start(task_id: int, db: Session = Depends(get_db)) -> WorkTaskTimerResponse:
    try:
        return _timer_resp(task_id, work_task_service.start_timer(db, task_id))
    except ValueError as exc:
        msg = str(exc)
        raise _not_found(task_id) if "not found" in msg else _conflict(msg)


@router.post("/{task_id}/timer/pause", response_model=WorkTaskTimerResponse)
def pause(task_id: int, db: Session = Depends(get_db)) -> WorkTaskTimerResponse:
    try:
        return _timer_resp(task_id, work_task_service.pause_timer(db, task_id))
    except ValueError as exc:
        msg = str(exc)
        raise _not_found(task_id) if "not found" in msg else _conflict(msg)


@router.post("/{task_id}/timer/resume", response_model=WorkTaskTimerResponse)
def resume(task_id: int, db: Session = Depends(get_db)) -> WorkTaskTimerResponse:
    try:
        return _timer_resp(task_id, work_task_service.resume_timer(db, task_id))
    except ValueError as exc:
        msg = str(exc)
        raise _not_found(task_id) if "not found" in msg else _conflict(msg)


@router.post("/{task_id}/timer/stop", response_model=WorkTaskTimerResponse)
def stop(task_id: int, db: Session = Depends(get_db)) -> WorkTaskTimerResponse:
    try:
        return _timer_resp(task_id, work_task_service.stop_timer(db, task_id))
    except ValueError as exc:
        msg = str(exc)
        raise _not_found(task_id) if "not found" in msg else _conflict(msg)
