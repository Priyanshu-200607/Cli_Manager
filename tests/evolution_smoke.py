from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.context_store import read_context, write_context
from src.core.context_gateway import ContextGateway
from src.core.critique_service import CritiqueService
from src.core.persistence.db_manager import DBManager
from src.core.event_bus import EventBus
from src.core.planner_service import PlannerService
from src.core.recovery_service import RecoveryService
from src.core.routing_service import RoutingService
from src.core.runtime_pool import RuntimePool
from src.core.task_engine import TaskEngine
from src.core.workspace_watcher import WorkspaceWatcher
from src.tui.components.dag_graph import render_dag_graph


def reset_state() -> None:
    # wipe the db clean before we start the test
    db = DBManager()
    db.clear_file_locks()
    db.clear_task_dependencies()
    for key, value in {
        "tasks": [],
        "task_history": [],
        "sessions": [],
        "context_slices": [],
        "global_context": {
            "id": "global",
            "owner": "orchestrator",
            "files": [],
            "memory": {},
            "shared_with": [],
            "version": 0,
        },
        "phase": "Evolution",
        "config": {
            "max_parallel_agents": 2,
            "log_level": "info",
            "workspace_root": str(ROOT),
        },
        "events": [],
        "fuel_ledger": [],
    }.items():
        write_context(key, value)


def pump(engine: TaskEngine, runtime: RuntimePool, recovery: RecoveryService, watcher: WorkspaceWatcher) -> None:
    # gotta keep the background stuff moving
    recovery.refresh_sessions()
    watcher.poll()
    engine.reconcile(runtime)


def wait_for(predicate, timeout: float = 30.0) -> None:
    # keep checking until the condition hits or we time out
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.2)
    raise TimeoutError("Timed out waiting for condition")


def main() -> int:
    reset_state()
    bus = EventBus()
    gateway = ContextGateway()
    recovery = RecoveryService(bus)
    runtime = RuntimePool(bus)
    engine = TaskEngine(bus, gateway, RoutingService(), PlannerService(), CritiqueService())
    watcher = WorkspaceWatcher(engine, ROOT)

    # kick off the initial planning task
    planning = engine.create_task(
        {
            "title": "Planning: Evolution Flow",
            "description": "Plan the evolution loop for critique and fuel.",
            "phase": 1,
        }
    )
    pump(engine, runtime, recovery, watcher)
    wait_for(
        lambda: (pump(engine, runtime, recovery, watcher) is None or True)
        and bool(next((task for task in (read_context("tasks") or []) if task["id"] == planning.id), {}).get("output_ref")),
        timeout=15,
    )
    engine.approve_blueprint(planning.id)

    wait_for(
        lambda: (
            pump(engine, runtime, recovery, watcher) is None
            or True
        )
        and any(task.get("metadata", {}).get("kind") == "critique" for task in (read_context("tasks") or [])),
        timeout=20,
    )
    wait_for(
        lambda: (
            pump(engine, runtime, recovery, watcher) is None
            or True
        )
        and any(task.get("metadata", {}).get("kind") == "autofix" for task in (read_context("tasks") or [])),
        timeout=30,
    )
    wait_for(
        lambda: (
            pump(engine, runtime, recovery, watcher) is None
            or True
        )
        and any(
            task.get("metadata", {}).get("kind") == "critique"
            and task["status"] == "done"
            and task["output_ref"]
            for task in (read_context("tasks") or [])
        ),
        timeout=30,
    )

    tasks = read_context("tasks") or []
    fuel_ledger = read_context("fuel_ledger") or []
    dependencies = read_context("task_dependencies") or []
    build_tasks = [task for task in tasks if task.get("metadata", {}).get("kind") == "building"]
    critique_tasks = [task for task in tasks if task.get("metadata", {}).get("kind") == "critique"]
    auto_fix_tasks = [task for task in tasks if task.get("metadata", {}).get("kind") == "autofix"]
    assert build_tasks
    assert critique_tasks
    assert auto_fix_tasks
    assert any(task["status"] in {"critique", "done", "failed"} for task in build_tasks)
    assert fuel_ledger
    assert all(entry["fuel"]["total_cost"] > 0 for entry in fuel_ledger)
    graph_panel = render_dag_graph(tasks, dependencies)
    assert "Planning: Evolution Flow" in str(graph_panel.renderable)
    assert any(dep["child_task_id"] == auto_fix_tasks[0]["id"] for dep in dependencies)
    print("evolution_smoke: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
