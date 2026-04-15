from __future__ import annotations

from rich.panel import Panel
from rich.table import Table


def render_task_detail(task: dict | None) -> Panel:
    # use a table to neatly align all the task info
    table = Table(show_header=False, box=None, expand=True)
    table.add_column("Field")
    table.add_column("Value")
    
    # if we don't have a task, just show a placeholder
    if task is None:
        table.add_row("Task", "No task selected")
    else:
        # otherwise dump out the important details
        table.add_row("Title", task["title"])
        table.add_row("Status", task["status"])
        table.add_row("Tool", task["assigned_tool"])
        table.add_row("Output", task.get("output_ref", "") or "-")
        table.add_row("Context", task["context_ref"])
        
    return Panel(table, title="Task Detail", border_style="yellow")
