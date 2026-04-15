from __future__ import annotations

import shutil
import subprocess
import threading
import uuid
from contextlib import suppress
from pathlib import Path
from time import time
from typing import Any

from src.core.context_store import read_context, replace_state
from src.core.event_bus import EventBus
from src.core.fuel_manager import FuelManager


ROOT = Path(__file__).resolve().parents[2]
SESSION_DIR = ROOT / "data" / "sessions"


class RuntimePool:
    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        self.processes: dict[str, subprocess.Popen[str]] = {}
        self.lock = threading.Lock()
        self.fuel_manager = FuelManager()
        SESSION_DIR.mkdir(parents=True, exist_ok=True)

    def spawn_agent(
        self,
        tool_type: str,
        context_id: str = "global",
        task_id: str | None = None,
        task_title: str | None = None,
    ) -> str:
        session_id = str(uuid.uuid4())
        command = self._resolve_command(tool_type)
        log_path = SESSION_DIR / f"{session_id}.log"
        
        # setup the tracking object before we actually kick off the process
        session = {
            "id": session_id,
            "name": task_title or f"{tool_type}-version-check",
            "active_tasks": [task_id] if task_id else [],
            "tool": tool_type,
            "started_at": time(),
            "last_ping": time(),
            "log_path": str(log_path),
            "state": "running",
            "context_id": context_id,
            "command": command,
            "output": "",
            "processed": False,
            "pid": None,
            "fuel": {"base_cost": 0, "output_tokens": 0, "total_cost": 0},
        }
        self._upsert_session(session)
        log_handle = log_path.open("w", encoding="utf-8")
        
        # start a detached session so we don't accidentally kill it if the cli goes down
        process = subprocess.Popen(
            command,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        with self.lock:
            self.processes[session_id] = process
        log_handle.close()
        session["pid"] = process.pid
        self._upsert_session(session)

        self.event_bus.publish(
            "AGENT_READY",
            {
                "source": "runtime_pool",
                "session_id": session_id,
                "tool": tool_type,
                "command": command,
            },
        )

        watcher = threading.Thread(
            target=self._watch_process,
            args=(session_id, process, log_path),
            daemon=True,
        )
        watcher.start()
        return session_id

    def kill_agent(self, session_id: str) -> bool:
        with self.lock:
            process = self.processes.get(session_id)
        sessions = read_context("sessions") or []
        if process is None:
            # check the db in case the process outlived our in-memory map
            session = next((item for item in sessions if item["id"] == session_id), None)
            if not session or not session.get("pid"):
                return False
            with suppress(ProcessLookupError):
                Path(session["log_path"]).touch(exist_ok=True)
                import os

                os.kill(session["pid"], 15)
            return True
        process.terminate()
        return True

    def get_active_sessions(self) -> list[dict[str, Any]]:
        sessions = read_context("sessions") or []
        return [session for session in sessions if session.get("state") == "running"]

    def _resolve_command(self, tool_type: str) -> list[str]:
        executable = shutil.which(tool_type)
        if not executable:
            raise FileNotFoundError(f"{tool_type} executable not found in PATH")
        return [executable, "--version"]

    def _watch_process(
        self,
        session_id: str,
        process: subprocess.Popen[str],
        log_path: Path,
    ) -> None:
        process.wait()
        output = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
        fuel = self.fuel_manager.calculate(
            next(
                (session["tool"] for session in (read_context("sessions") or []) if session["id"] == session_id),
                "unassigned",
            ),
            output.strip(),
        )

        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            sessions = state.get("sessions", [])
            for session in sessions:
                if session["id"] == session_id:
                    session["last_ping"] = time()
                    session["state"] = "completed" if process.returncode == 0 else "error"
                    session["output"] = output.strip()
                    session["fuel"] = fuel
            state["events"] = state.get("events", [])
            state["events"].append(
                {
                    "topic": "PROCESS_OUTPUT",
                    "session_id": session_id,
                    "output": output.strip(),
                    "returncode": process.returncode,
                }
            )
            state["fuel_ledger"] = state.get("fuel_ledger", [])
            state["fuel_ledger"].append(
                {
                    "session_id": session_id,
                    "fuel": fuel,
                    "timestamp": time(),
                }
            )
            return state

        replace_state(mutate)
        self.event_bus.publish(
            "PROCESS_OUTPUT",
            {
                "source": "runtime_pool",
                "session_id": session_id,
                "output": output.strip(),
                "returncode": process.returncode,
            },
        )
        with self.lock:
            self.processes.pop(session_id, None)

    def _upsert_session(self, candidate: dict[str, Any]) -> None:
        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            sessions = state.get("sessions", [])
            sessions = [session for session in sessions if session["id"] != candidate["id"]]
            sessions.append(candidate)
            state["sessions"] = sessions
            return state

        replace_state(mutate)
