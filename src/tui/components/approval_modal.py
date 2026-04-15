from __future__ import annotations

from rich.panel import Panel
from rich.text import Text


def render_approval_modal(task: dict | None) -> Panel | None:
    # bail early if there's no task selected
    if task is None:
        return None
    
    metadata = task.get("metadata", {})
    # we only care about planning tasks that haven't been approved yet
    if metadata.get("kind") != "planning" or metadata.get("blueprint_approved"):
        return None
    
    if not task.get("output_ref"):
        return None
        
    # show a nice clear prompt for the user
    body = Text(
        f"Blueprint ready for approval.\nTask: {task['title']}\nArtifact: {task['output_ref']}\nPress a to approve building tasks.",
        style="bold",
    )
    return Panel(body, title="Approval Required", border_style="red")
