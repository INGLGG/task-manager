import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from task_manager.api.main import app
from task_manager.db.database import get_db
from task_manager.models.task import Base


@pytest.fixture()
def client():
    # StaticPool ensures create_all and all sessions share the same in-memory DB.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_create_and_list(client) -> None:
    resp = client.post("/tasks/", json={"title": "Test task", "priority": "high"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Test task"
    assert data["priority"] == "high"

    resp = client.get("/tasks/")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_get_task(client) -> None:
    task_id = client.post("/tasks/", json={"title": "Get me"}).json()["id"]
    resp = client.get(f"/tasks/{task_id}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Get me"


def test_get_task_not_found(client) -> None:
    assert client.get("/tasks/999").status_code == 404


def test_update_task(client) -> None:
    task_id = client.post("/tasks/", json={"title": "Old title"}).json()["id"]
    resp = client.patch(f"/tasks/{task_id}", json={"status": "done"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "done"


def test_delete_task(client) -> None:
    task_id = client.post("/tasks/", json={"title": "Delete me"}).json()["id"]
    assert client.delete(f"/tasks/{task_id}").status_code == 204
    assert client.get(f"/tasks/{task_id}").status_code == 404
