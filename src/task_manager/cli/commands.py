from datetime import datetime
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from task_manager.db.database import SessionLocal, init_db
from task_manager.models.task import Priority, Status
from task_manager.services import task_service, timer_service

app = typer.Typer(help="Task Manager CLI")
timer_app = typer.Typer(help="Timer commands")
app.add_typer(timer_app, name="timer")
console = Console()

DATE_FORMAT = "%Y-%m-%d"


def _db():
    init_db()
    return SessionLocal()


@app.command("list")
def list_tasks() -> None:
    """List all tasks."""
    db = _db()
    tasks = task_service.get_all(db)
    db.close()

    table = Table(title="Tasks")
    table.add_column("ID", style="cyan")
    table.add_column("Title")
    table.add_column("Status", style="green")
    table.add_column("Priority", style="yellow")
    table.add_column("Due Date")

    for t in tasks:
        table.add_row(
            str(t.id),
            t.title,
            t.status.value,
            t.priority.value,
            str(t.due_date.date()) if t.due_date else "-",
        )

    console.print(table)


@app.command("add")
def add_task(
    title: str = typer.Argument(..., help="Task title"),
    description: Optional[str] = typer.Option(None, "--desc", "-d"),
    priority: Priority = typer.Option(Priority.medium, "--priority", "-p"),
    due_date: Optional[datetime] = typer.Option(None, "--due", formats=["%Y-%m-%d"]),
) -> None:
    """Create a new task."""
    db = _db()
    task = task_service.create(db, title, description, priority, due_date)
    db.close()
    console.print(f"[green]Task #{task.id} created:[/green] {task.title}")


@app.command("done")
def mark_done(task_id: int = typer.Argument(..., help="Task ID")) -> None:
    """Mark a task as done."""
    db = _db()
    task = task_service.update(db, task_id, status=Status.done)
    db.close()
    if not task:
        console.print(f"[red]Task #{task_id} not found.[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Task #{task_id} marked as done.[/green]")


@app.command("delete")
def delete_task(task_id: int = typer.Argument(..., help="Task ID")) -> None:
    """Delete a task."""
    db = _db()
    deleted = task_service.delete(db, task_id)
    db.close()
    if not deleted:
        console.print(f"[red]Task #{task_id} not found.[/red]")
        raise typer.Exit(1)
    console.print(f"[red]Task #{task_id} deleted.[/red]")


@app.command("show")
def show_task(task_id: int = typer.Argument(..., help="Task ID")) -> None:
    """Show details of a single task."""
    db = _db()
    task = task_service.get_by_id(db, task_id)
    db.close()
    if not task:
        console.print(f"[red]Task #{task_id} not found.[/red]")
        raise typer.Exit(1)

    table = Table(show_header=False, box=None)
    table.add_column("Field", style="cyan", min_width=12)
    table.add_column("Value")
    table.add_row("ID", str(task.id))
    table.add_row("Title", task.title)
    table.add_row("Description", task.description or "-")
    table.add_row("Status", task.status.value)
    table.add_row("Priority", task.priority.value)
    table.add_row("Due Date", str(task.due_date.date()) if task.due_date else "-")
    table.add_row("Created", str(task.created_at.date()))
    table.add_row("Updated", str(task.updated_at.date()))
    console.print(table)


def _fmt_elapsed(seconds: float) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


@timer_app.command("start")
def timer_start(task_id: int = typer.Argument(..., help="Task ID")) -> None:
    """Start the timer for a task."""
    db = _db()
    try:
        task = timer_service.start_timer(db, task_id)
        db.close()
        console.print(f"[green]Timer started for task #{task.id}.[/green]")
    except ValueError as exc:
        db.close()
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)


@timer_app.command("pause")
def timer_pause(task_id: int = typer.Argument(..., help="Task ID")) -> None:
    """Pause the timer for a task."""
    db = _db()
    try:
        task = timer_service.pause_timer(db, task_id)
        db.close()
        console.print(
            f"[yellow]Timer paused for task #{task.id}. "
            f"Elapsed: {_fmt_elapsed(task.elapsed_seconds)}[/yellow]"
        )
    except ValueError as exc:
        db.close()
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)


@timer_app.command("resume")
def timer_resume(task_id: int = typer.Argument(..., help="Task ID")) -> None:
    """Resume a paused timer."""
    db = _db()
    try:
        task = timer_service.resume_timer(db, task_id)
        db.close()
        console.print(f"[green]Timer resumed for task #{task.id}.[/green]")
    except ValueError as exc:
        db.close()
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)


@timer_app.command("stop")
def timer_stop(task_id: int = typer.Argument(..., help="Task ID")) -> None:
    """Stop the timer and finalise elapsed time."""
    db = _db()
    try:
        task = timer_service.stop_timer(db, task_id)
        db.close()
        console.print(
            f"[red]Timer stopped for task #{task.id}. "
            f"Total: {_fmt_elapsed(task.elapsed_seconds)}[/red]"
        )
    except ValueError as exc:
        db.close()
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)


@timer_app.command("status")
def timer_status_cmd(task_id: int = typer.Argument(..., help="Task ID")) -> None:
    """Show current timer status and elapsed time."""
    db = _db()
    task = task_service.get_by_id(db, task_id)
    if not task:
        db.close()
        console.print(f"[red]Task #{task_id} not found.[/red]")
        raise typer.Exit(1)
    elapsed = timer_service.get_elapsed(task)
    db.close()
    console.print(
        f"Task #{task_id} · status=[cyan]{task.timer_status.value}[/cyan] · "
        f"elapsed={_fmt_elapsed(elapsed)}"
    )


@app.command("update")
def update_task(
    task_id: int = typer.Argument(..., help="Task ID"),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="New title"),
    description: Optional[str] = typer.Option(None, "--desc", "-d", help="New description"),
    status: Optional[Status] = typer.Option(None, "--status", "-s", help="New status"),
    priority: Optional[Priority] = typer.Option(None, "--priority", "-p", help="New priority"),
    due_date: Optional[datetime] = typer.Option(None, "--due", formats=[DATE_FORMAT], help="New due date (YYYY-MM-DD)"),
) -> None:
    """Update fields on an existing task."""
    updates = {k: v for k, v in {
        "title": title,
        "description": description,
        "status": status,
        "priority": priority,
        "due_date": due_date,
    }.items() if v is not None}

    if not updates:
        console.print("[yellow]No fields provided — nothing to update.[/yellow]")
        raise typer.Exit(0)

    db = _db()
    task = task_service.update(db, task_id, **updates)
    db.close()
    if not task:
        console.print(f"[red]Task #{task_id} not found.[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Task #{task_id} updated.[/green]")
