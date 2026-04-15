from __future__ import annotations

import argparse
import select
import sys
import termios
import time
import tty
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rich.columns import Columns
from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.core.context_store import read_context
from src.core.context_gateway import ContextGateway
from src.core.event_bus import EventBus
from src.core.planner_service import PlannerService
from src.core.recovery_service import RecoveryService
from src.core.runtime_pool import RuntimePool
from src.core.routing_service import RoutingService
from src.core.critique_service import CritiqueService
from src.core.task_engine import TaskEngine
from src.core.workspace_watcher import WorkspaceWatcher
from src.tui.components.approval_modal import render_approval_modal
from src.tui.components.dag_graph import render_dag_graph
from src.tui.components.log_viewer import render_log_viewer
from src.tui.components.task_detail import render_task_detail


def build_layout(selected_task_index: int = 0, selected_session_index: int = 0, mode: str = "board") -> Group:
    # grab all the current state to render the UI
    tasks = read_context("tasks") or []
    sessions = read_context("sessions") or []
    events = read_context("events") or []
    dependencies = read_context("task_dependencies") or []
    fuel_ledger = read_context("fuel_ledger") or []
    selected_task = tasks[selected_task_index] if tasks and selected_task_index < len(tasks) else None
    selected_session = (
        sessions[selected_session_index] if sessions and selected_session_index < len(sessions) else None
    )

    lanes = {
        "Pending": [task for task in tasks if task["status"] in {"pending", "blocked", "failed"}],
        "In Progress": [task for task in tasks if task["status"] == "in_progress"],
        "Done": [task for task in tasks if task["status"] == "done"],
    }
    lane_panels = []
    for title, items in lanes.items():
        lane_table = Table(expand=True, show_header=False, box=None)
        lane_table.add_column("Task")
        if items:
            for task in items:
                metadata = task.get("metadata", {})
                suffix = ""
                if metadata.get("kind") == "building" and metadata.get("approval_required"):
                    suffix = " [approval]"
                lane_table.add_row(f"{task['title']} [{task['assigned_tool']}] {suffix}".strip())
        else:
            lane_table.add_row("No tasks")
        lane_panels.append(Panel(lane_table, title=title, border_style="cyan"))

    session_table = Table(title="Active Sessions", expand=True)
    session_table.add_column("Session")
    session_table.add_column("Tool")
    session_table.add_column("State")
    if sessions:
        for session in sessions:
            session_table.add_row(session["name"], session["tool"], session["state"])
    else:
        session_table.add_row("No sessions", "-", "-")

    detail_panel = render_log_viewer(selected_session) if mode == "log" else render_task_detail(selected_task)
    approval_panel = render_approval_modal(selected_task)
    dag_panel = render_dag_graph(tasks, dependencies)
    fuel_total = sum(entry.get("fuel", {}).get("total_cost", 0) for entry in fuel_ledger)
    right_panels = [detail_panel, dag_panel]
    if approval_panel is not None and mode != "log":
        right_panels.append(approval_panel)
    latest_event = events[-1] if events else {}
    status = Text(
        f"Phase Evolution | Active Sessions: {sum(1 for s in sessions if s['state'] == 'running')} | Fuel: {fuel_total} | "
        f"Latest Event: {latest_event.get('topic', 'none')} | Press n new task | a approve | j/k select | l log | b board | q quit",
        style="bold white on blue",
    )
    return Group(
        Columns(lane_panels, equal=True, expand=True),
        Columns(
            [
                Panel(session_table, border_style="green"),
                Group(*right_panels),
            ],
            equal=True,
            expand=True,
        ),
        Panel(status, border_style="blue"),
    )


def run_tui(
    auto_spawn: bool = False,
    auto_quit_after: float | None = None,
    create_task_title: str | None = None,
    create_task_description: str | None = None,
) -> int:
    bus = EventBus()
    runtime = RuntimePool(bus)
    recovery = RecoveryService(bus)
    task_engine = TaskEngine(bus, ContextGateway(), RoutingService(), PlannerService(), CritiqueService())
    watcher = WorkspaceWatcher(task_engine, ROOT)
    selected_task_index = 0
    selected_session_index = 0
    mode = "board"

    # auto spawn a demo task if requested
    if auto_spawn:
        task_engine.create_task(
            {
                "title": "Planning: Demo Task",
                "description": "Plan the implementation for the demo board.",
                "phase": 1,
            }
        )
    if create_task_title and create_task_description:
        task_engine.create_task(
            {
                "title": create_task_title,
                "description": create_task_description,
                "phase": 1,
            }
        )

    is_tty = sys.stdin.isatty()
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd) if is_tty else None
    start = time.time()

    def _noop(_: dict[str, object]) -> None:
        return

    bus.subscribe("AGENT_READY", _noop)
    bus.subscribe("PROCESS_OUTPUT", _noop)

    try:
        if is_tty:
            tty.setcbreak(fd)
        recovery.recover_active_agents()
        with Live(build_layout(), refresh_per_second=4, screen=True) as live:
            # main UI loop
            while True:
                recovery.refresh_sessions()
                watcher.poll()
                task_engine.reconcile(runtime)
                tasks = read_context("tasks") or []
                sessions = read_context("sessions") or []
                if tasks:
                    selected_task_index = min(selected_task_index, len(tasks) - 1)
                else:
                    selected_task_index = 0
                if sessions:
                    selected_session_index = min(selected_session_index, len(sessions) - 1)
                else:
                    selected_session_index = 0
                live.update(build_layout(selected_task_index, selected_session_index, mode))
                if auto_quit_after is not None and (time.time() - start) >= auto_quit_after:
                    break
                if is_tty:
                    # check for user input without blocking
                    ready, _, _ = select.select([sys.stdin], [], [], 0.25)
                    if ready:
                        char = sys.stdin.read(1)
                        if char.lower() == "q":
                            break
                        if char.lower() == "n":
                            task_engine.create_task(
                                {
                                    "title": "Planning: Interactive Task",
                                    "description": "Plan the next implementation step for the board.",
                                    "phase": 1,
                                }
                            )
                        if char.lower() == "a" and tasks:
                            try:
                                task_engine.approve_blueprint(tasks[selected_task_index]["id"])
                            except ValueError:
                                pass
                        if char.lower() == "j":
                            if mode == "log":
                                selected_session_index += 1
                            else:
                                selected_task_index += 1
                        if char.lower() == "k":
                            if mode == "log":
                                selected_session_index = max(0, selected_session_index - 1)
                            else:
                                selected_task_index = max(0, selected_task_index - 1)
                        if char.lower() == "l":
                            mode = "log"
                        if char.lower() == "b":
                            mode = "board"
                else:
                    time.sleep(0.25)
        return 0
    finally:
        # always restore terminal settings
        if old_settings is not None:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def main() -> int:
    parser = argparse.ArgumentParser(description="CLI Manager Evolution TUI")
    parser.add_argument("--demo", action="store_true", help="Create a planning task on startup")
    parser.add_argument("--create-task-title", default=None, help="Create a task before the TUI starts")
    parser.add_argument(
        "--create-task-description",
        default=None,
        help="Description for the startup task",
    )
    parser.add_argument(
        "--auto-quit-after",
        type=float,
        default=None,
        help="Exit automatically after the given number of seconds",
    )
    args = parser.parse_args()
    return run_tui(
        auto_spawn=args.demo,
        auto_quit_after=args.auto_quit_after,
        create_task_title=args.create_task_title,
        create_task_description=args.create_task_description,
    )


if __name__ == "__main__":
    raise SystemExit(main())
