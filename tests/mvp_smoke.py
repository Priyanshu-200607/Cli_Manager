from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.context_store import STORE_PATH, read_context, write_context
from src.core.context_gateway import ContextGateway
from src.core.event_bus import EventBus
from src.core.routing_service import RoutingService
from src.core.runtime_pool import RuntimePool
from src.core.task_engine import TaskEngine


def reset_state() -> None:
    # flush everything so the test runs perfectly clean
    write_context("tasks", [])
    write_context("task_history", [])
    write_context("sessions", [])
    write_context("context_slices", [])
    write_context(
        "global_context",
        {
            "id": "global",
            "owner": "orchestrator",
            "files": [],
            "memory": {},
            "shared_with": [],
            "version": 0,
        },
    )
    write_context("phase", "MVP")
    write_context(
        "config",
        {
            "max_parallel_agents": 2,
            "log_level": "info",
            "workspace_root": str(ROOT),
        },
    )
    write_context("events", [])


def main() -> int:
    reset_state()
    bus = EventBus()
    runtime = RuntimePool(bus)
    engine = TaskEngine(bus, ContextGateway(), RoutingService())

    planning = engine.create_task(
        {
            "title": "Planning: Build the Kanban flow",
            "description": "Plan and analyze the build sequence for the orchestration MVP.",
            "phase": 1,
        }
    )
    assert planning.assigned_tool == "gemini"

    # give the pipeline a little bit to crank through the steps
    deadline = time.time() + 15
    while time.time() < deadline:
        engine.reconcile(runtime)
        tasks = read_context("tasks") or []
        if len(tasks) >= 2 and all(task["status"] == "done" for task in tasks):
            break
        time.sleep(0.2)
    else:
        raise TimeoutError("Timed out waiting for MVP orchestration flow")

    tasks = read_context("tasks") or []
    sessions = read_context("sessions") or []
    history = read_context("task_history") or []
    assert len(tasks) == 2
    planning_task = next(task for task in tasks if task["assigned_tool"] == "gemini")
    building_task = next(task for task in tasks if task["assigned_tool"] == "codex")
    assert Path(ROOT / planning_task["output_ref"]).exists()
    assert Path(ROOT / building_task["output_ref"]).exists()
    
    # check that the planning agent actually created a valid blueprint
    blueprint = json.loads((ROOT / planning_task["output_ref"]).read_text(encoding="utf-8"))
    assert "implementation_steps" in blueprint
    assert any(session["tool"] == "gemini" for session in sessions)
    assert any(session["tool"] == "codex" for session in sessions)
    assert history

    payload = json.loads(STORE_PATH.read_text(encoding="utf-8"))
    assert payload["tasks"]
    assert payload["task_history"]
    print("mvp_smoke: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
