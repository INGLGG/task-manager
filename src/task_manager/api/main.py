from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI

from task_manager.api.routes import tasks
from task_manager.api.routes import timer
from task_manager.api.routes import work_tasks
from task_manager.config import settings
from task_manager.db.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
app.include_router(timer.router, prefix="/tasks/{task_id}/timer", tags=["timer"])
app.include_router(work_tasks.router, prefix="/work-tasks", tags=["work-tasks"])
