from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.context_store import STORE_PATH, read_context, write_context
from src.core.context_gateway import ContextGateway
from src.core.event_bus import EventBus
from src.core.planner_service import PlannerService
from src.core.recovery_service import RecoveryService
from src.core.routing_service import RoutingService
from src.core.runtime_pool import RuntimePool
from src.core.task_engine import TaskEngine
from src.core.workspace_watcher import WorkspaceWatcher


def reset_state() -> None:
    # reset all the global contexts for a fresh test run
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
        "phase": "Production",
        "config": {
            "max_parallel_agents": 2,
            "log_level": "info",
            "workspace_root": str(ROOT),
        },
        "events": [],
    }.items():
        write_context(key, value)


def pump(engine: TaskEngine, runtime: RuntimePool, recovery: RecoveryService, watcher: WorkspaceWatcher) -> None:
    recovery.refresh_sessions()
    watcher.poll()
    engine.reconcile(runtime)


def wait_for(predicate, timeout: float = 20.0) -> None:
    # standard polling loop with a timeout to catch stuck processes
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
    engine = TaskEngine(bus, gateway, RoutingService(), PlannerService())
    watcher = WorkspaceWatcher(engine, ROOT)

    planning = engine.create_task(
        {
            "title": "Planning: Production DAG",
            "description": "Plan the production DAG for the orchestrator.",
            "phase": 1,
        }
    )
    pump(engine, runtime, recovery, watcher)
    wait_for(
        lambda: (pump(engine, runtime, recovery, watcher) is None or True)
        and bool(next((task for task in (read_context("tasks") or []) if task["id"] == planning.id), {}).get("output_ref")),
        timeout=15,
    )

    tasks = read_context("tasks") or []
    build_tasks = [task for task in tasks if task.get("metadata", {}).get("kind") == "building"]
    assert len(build_tasks) >= 3
    assert all(task["status"] == "blocked" for task in build_tasks)

    dependencies = read_context("task_dependencies") or []
    assert dependencies
    with sqlite3.connect(STORE_PATH) as connection:
        row = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'task_dependencies'"
        ).fetchone()
        assert row

    # kick off the real build phase now
    engine.approve_blueprint(planning.id)
    wait_for(
        lambda: (
            pump(engine, runtime, recovery, watcher) is None
            or True
        )
        and all(
            task["status"] == "done"
            for task in (read_context("tasks") or [])
            if task.get("metadata", {}).get("kind") == "building"
        ),
        timeout=25,
    )

    # mess with a file to see if the watcher catches it
    original = (ROOT / "src" / "models" / "dag.py").read_text(encoding="utf-8")
    pump(engine, runtime, recovery, watcher)
    try:
        (ROOT / "src" / "models" / "dag.py").write_text(original + "\n# validation-trigger\n", encoding="utf-8")
        wait_for(
            lambda: (
                pump(engine, runtime, recovery, watcher) is None
                or True
            )
            and any(
                task.get("metadata", {}).get("kind") == "validation"
                for task in (read_context("tasks") or [])
            ),
            timeout=10,
        )
    finally:
        (ROOT / "src" / "models" / "dag.py").write_text(original, encoding="utf-8")

    updated_planning = next(task for task in (read_context("tasks") or []) if task["id"] == planning.id)
    assert updated_planning["metadata"]["blueprint_approved"] is True
    assert any(task.get("metadata", {}).get("kind") == "validation" for task in (read_context("tasks") or []))
    print("production_smoke: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
