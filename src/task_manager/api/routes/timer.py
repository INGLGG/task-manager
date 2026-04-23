from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from task_manager.db.database import get_db
from task_manager.models.task import TimerStatus
from task_manager.services import timer_service

router = APIRouter()


class TimerResponse(BaseModel):
    task_id: int
    timer_status: TimerStatus
    elapsed_seconds: float

    model_config = {"from_attributes": True}


def _timer_response(task_id: int, task: object) -> TimerResponse:
    return TimerResponse(
        task_id=task_id,
        timer_status=task.timer_status,  # type: ignore[attr-defined]
        elapsed_seconds=timer_service.get_elapsed(task),  # type: ignore[arg-type]
    )


def _not_found(task_id: int) -> HTTPException:
    return HTTPException(status_code=404, detail=f"Task {task_id} not found")


def _conflict(msg: str) -> HTTPException:
    return HTTPException(status_code=409, detail=msg)


@router.get("/", response_model=TimerResponse)
def get_timer(task_id: int, db: Session = Depends(get_db)) -> TimerResponse:
    from task_manager.services import task_service
    task = task_service.get_by_id(db, task_id)
    if task is None:
        raise _not_found(task_id)
    return _timer_response(task_id, task)


@router.post("/start", response_model=TimerResponse)
def start(task_id: int, db: Session = Depends(get_db)) -> TimerResponse:
    try:
        task = timer_service.start_timer(db, task_id)
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg:
            raise _not_found(task_id)
        raise _conflict(msg)
    return _timer_response(task_id, task)


@router.post("/pause", response_model=TimerResponse)
def pause(task_id: int, db: Session = Depends(get_db)) -> TimerResponse:
    try:
        task = timer_service.pause_timer(db, task_id)
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg:
            raise _not_found(task_id)
        raise _conflict(msg)
    return _timer_response(task_id, task)


@router.post("/resume", response_model=TimerResponse)
def resume(task_id: int, db: Session = Depends(get_db)) -> TimerResponse:
    try:
        task = timer_service.resume_timer(db, task_id)
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg:
            raise _not_found(task_id)
        raise _conflict(msg)
    return _timer_response(task_id, task)


@router.post("/stop", response_model=TimerResponse)
def stop(task_id: int, db: Session = Depends(get_db)) -> TimerResponse:
    try:
        task = timer_service.stop_timer(db, task_id)
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg:
            raise _not_found(task_id)
        raise _conflict(msg)
    return _timer_response(task_id, task)
