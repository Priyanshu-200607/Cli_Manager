from __future__ import annotations

from rich.panel import Panel
from rich.text import Text


def render_dag_graph(tasks: list[dict], dependencies: list[dict]) -> Panel:
    # quickly index tasks by id so we don't have to scan the list repeatedly
    task_by_id = {task["id"]: task for task in tasks}
    children: dict[str, list[str]] = {}
    parents: set[str] = set()
    
    # build out the graph edges
    for dep in dependencies:
        children.setdefault(dep["parent_task_id"], []).append(dep["child_task_id"])
        parents.add(dep["child_task_id"])

    # find the root nodes (tasks that nothing depends on)
    roots = [task["id"] for task in tasks if task["id"] not in parents]
    lines: list[str] = []

    def walk(task_id: str, prefix: str = "") -> None:
        task = task_by_id.get(task_id)
        if not task:
            return
        lines.append(f"{prefix}{task['title']} [{task['status']}]")
        for child_id in children.get(task_id, []):
            walk(child_id, prefix + "  ")

    for root_id in roots:
        walk(root_id)
        
    # show a message if there are no nodes to display
    if not lines:
        lines.append("No dependency graph")
        
    return Panel(Text("\n".join(lines)), title="DAG Graph", border_style="magenta")
