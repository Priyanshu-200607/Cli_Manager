from __future__ import annotations

import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.context_store import STORE_PATH, read_context, write_context
from src.core.context_gateway import ContextGateway
from src.core.event_bus import EventBus
from src.core.recovery_service import RecoveryService
from src.core.routing_service import RoutingService
from src.core.runtime_pool import RuntimePool
from src.core.task_engine import TaskEngine
from src.tui.components.log_viewer import render_log_viewer


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
        "phase": "Scale",
        "config": {
            "max_parallel_agents": 2,
            "log_level": "info",
            "workspace_root": str(ROOT),
        },
        "events": [],
    }.items():
        write_context(key, value)


def wait_for(predicate, timeout: float = 10.0) -> None:
    # standard polling loop with a timeout to catch stuck processes
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.1)
    raise TimeoutError("Timed out waiting for condition")


def pump(engine: TaskEngine, runtime: RuntimePool, recovery: RecoveryService) -> None:
    # tick the state machine forward
    recovery.refresh_sessions()
    engine.reconcile(runtime)


def main() -> int:
    reset_state()
    assert Path(STORE_PATH).exists()
    with sqlite3.connect(STORE_PATH) as connection:
        row = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'state_store'").fetchone()
        assert row

    bus = EventBus()
    gateway = ContextGateway()
    runtime = RuntimePool(bus)
    recovery = RecoveryService(bus)
    engine = TaskEngine(bus, gateway, RoutingService())

    planning = engine.create_task(
        {
            "title": "Planning: Recoverable task",
            "description": "Plan and analyze the recoverable orchestration flow.",
            "phase": 1,
        }
    )
    pump(engine, runtime, recovery)
    wait_for(lambda: any(session["tool"] == "gemini" for session in (read_context("sessions") or [])))
    wait_for(
        lambda: (pump(engine, runtime, recovery) is None or True)
        and any(task["assigned_tool"] == "codex" for task in (read_context("tasks") or [])),
        timeout=15,
    )

    slow_log = ROOT / "data" / "sessions" / "recovery-test.log"
    slow_process = subprocess.Popen(
        [sys.executable, "-c", "import time; print('recovery-start', flush=True); time.sleep(3); print('recovery-done', flush=True)"],
        stdout=slow_log.open("w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    sessions = read_context("sessions") or []
    sessions.append(
        {
            "id": "recovery-session",
            "name": "Recovery Session",
            "active_tasks": [],
            "tool": "gemini",
            "started_at": time.time(),
            "last_ping": time.time(),
            "log_path": str(slow_log),
            "state": "running",
            "context_id": "global",
            "command": [sys.executable, "-c", "sleep"],
            "output": "",
            "processed": False,
            "pid": slow_process.pid,
        }
    )
    write_context("sessions", sessions)
    recovery.recover_active_agents()
    assert any(session["id"] == "recovery-session" and session["state"] == "running" for session in (read_context("sessions") or []))
    wait_for(lambda: slow_process.poll() is not None, timeout=8)
    wait_for(
        lambda: (
            pump(engine, runtime, recovery) is None
            or True
        )
        and "recovery-done"
        in next(
            session for session in (read_context("sessions") or []) if session["id"] == "recovery-session"
        )["output"],
        timeout=8,
    )
    recovered = next(session for session in (read_context("sessions") or []) if session["id"] == "recovery-session")
    assert recovered["state"] == "completed"
    assert "recovery-done" in recovered["output"]

    build_tasks = [task for task in (read_context("tasks") or []) if task["assigned_tool"] == "codex"]
    assert build_tasks
    conflicting = engine.create_task(
        {
            "title": "Building: Conflict Task",
            "description": "Implement blueprint from an existing artifact",
            "phase": 1,
            "assigned_tool": "codex",
        }
    )
    first_build = build_tasks[0]
    first_slice = gateway.get_slice(first_build["context_ref"])
    conflict_slice = gateway.get_slice(conflicting.context_ref)
    assert first_slice and conflict_slice
    gateway.commit_slice(conflict_slice.id, {"files": first_slice.files or ["src/core/task_engine.py"]})
    assert gateway.claim_files(first_build["id"], first_slice.id, first_slice.files or ["src/core/task_engine.py"])
    pump(engine, runtime, recovery)
    conflict_task = next(task for task in (read_context("tasks") or []) if task["id"] == conflicting.id)
    assert conflict_task["status"] == "blocked"
    gateway.release_files(first_build["id"])

    # verify the log viewer picks up the recovered output
    panel = render_log_viewer(recovered)
    assert "recovery-done" in str(panel.renderable)
    print("scale_smoke: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
