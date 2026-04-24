from datetime import datetime
from unittest.mock import patch

from typer.testing import CliRunner

from task_manager.cli.commands import app
from task_manager.models.task import Priority, Status, Task

runner = CliRunner()


def _make_task(**kwargs) -> Task:
    defaults = dict(id=1, title="Sample", description=None, status=Status.todo,
                    priority=Priority.medium,
                    created_at=datetime(2024, 1, 1), updated_at=datetime(2024, 1, 2))
    defaults.update(kwargs)
    t = Task(**{k: v for k, v in defaults.items() if k not in ("id", "created_at", "updated_at")})
    t.id = defaults["id"]
    t.created_at = defaults["created_at"]
    t.updated_at = defaults["updated_at"]
    return t


@patch("task_manager.cli.commands.task_service.get_all")
@patch("task_manager.cli.commands.SessionLocal")
@patch("task_manager.cli.commands.init_db")
def test_list(mock_init, mock_session, mock_get_all) -> None:
    mock_get_all.return_value = [_make_task(title="My task")]
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "My task" in result.output


@patch("task_manager.cli.commands.task_service.create")
@patch("task_manager.cli.commands.SessionLocal")
@patch("task_manager.cli.commands.init_db")
def test_add(mock_init, mock_session, mock_create) -> None:
    mock_create.return_value = _make_task(title="New task")
    result = runner.invoke(app, ["add", "New task"])
    assert result.exit_code == 0
    assert "New task" in result.output


@patch("task_manager.cli.commands.task_service.get_by_id")
@patch("task_manager.cli.commands.SessionLocal")
@patch("task_manager.cli.commands.init_db")
def test_show(mock_init, mock_session, mock_get) -> None:
    mock_get.return_value = _make_task(title="Detail task", description="Some desc")
    result = runner.invoke(app, ["show", "1"])
    assert result.exit_code == 0
    assert "Detail task" in result.output
    assert "Some desc" in result.output


@patch("task_manager.cli.commands.task_service.get_by_id")
@patch("task_manager.cli.commands.SessionLocal")
@patch("task_manager.cli.commands.init_db")
def test_show_not_found(mock_init, mock_session, mock_get) -> None:
    mock_get.return_value = None
    result = runner.invoke(app, ["show", "99"])
    assert result.exit_code == 1
    assert "not found" in result.output


@patch("task_manager.cli.commands.task_service.update")
@patch("task_manager.cli.commands.SessionLocal")
@patch("task_manager.cli.commands.init_db")
def test_update_title(mock_init, mock_session, mock_update) -> None:
    mock_update.return_value = _make_task(title="Updated title")
    result = runner.invoke(app, ["update", "1", "--title", "Updated title"])
    assert result.exit_code == 0
    assert "updated" in result.output
    mock_update.assert_called_once()
    _, kwargs = mock_update.call_args
    assert kwargs.get("title") == "Updated title"


@patch("task_manager.cli.commands.task_service.update")
@patch("task_manager.cli.commands.SessionLocal")
@patch("task_manager.cli.commands.init_db")
def test_update_status(mock_init, mock_session, mock_update) -> None:
    mock_update.return_value = _make_task(status=Status.in_progress)
    result = runner.invoke(app, ["update", "1", "--status", "in_progress"])
    assert result.exit_code == 0
    _, kwargs = mock_update.call_args
    assert kwargs.get("status") == Status.in_progress


@patch("task_manager.cli.commands.task_service.update")
@patch("task_manager.cli.commands.SessionLocal")
@patch("task_manager.cli.commands.init_db")
def test_update_no_fields(mock_init, mock_session, mock_update) -> None:
    result = runner.invoke(app, ["update", "1"])
    assert result.exit_code == 0
    assert "nothing to update" in result.output
    mock_update.assert_not_called()


@patch("task_manager.cli.commands.task_service.update")
@patch("task_manager.cli.commands.SessionLocal")
@patch("task_manager.cli.commands.init_db")
def test_update_not_found(mock_init, mock_session, mock_update) -> None:
    mock_update.return_value = None
    result = runner.invoke(app, ["update", "99", "--title", "X"])
    assert result.exit_code == 1
    assert "not found" in result.output
