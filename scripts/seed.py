"""Populate the database with sample tasks for development."""
from datetime import datetime, timedelta

from task_manager.db.database import SessionLocal, init_db
from task_manager.models.task import Priority
from task_manager.services import task_service

SAMPLE_TASKS = [
    {
        "title": "Set up CI/CD pipeline",
        "description": "Configure GitHub Actions for lint, test, and deploy.",
        "priority": Priority.high,
        "due_date": datetime.now() + timedelta(days=3),
    },
    {
        "title": "Write API documentation",
        "description": "Document all endpoints in OpenAPI format.",
        "priority": Priority.medium,
        "due_date": datetime.now() + timedelta(days=7),
    },
    {
        "title": "Add pagination to task list",
        "description": "Support limit/offset query params on GET /tasks.",
        "priority": Priority.low,
        "due_date": None,
    },
]


def main() -> None:
    init_db()
    db = SessionLocal()
    for data in SAMPLE_TASKS:
        task_service.create(db, **data)
        print(f"Created: {data['title']}")
    db.close()
    print("Seed complete.")


if __name__ == "__main__":
    main()
