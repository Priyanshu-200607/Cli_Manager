from __future__ import annotations

import os
from pathlib import Path
from time import time
from typing import Any

from src.core.context_store import read_context, replace_state
from src.core.event_bus import EventBus


class RecoveryService:
    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus

    def recover_active_agents(self) -> list[dict[str, Any]]:
        # sync our internal tracking with the actual OS processes
        sessions = read_context("sessions") or []
        return [self._refresh_session(session) for session in sessions if session.get("state") == "running"]

    def refresh_sessions(self) -> None:
        sessions = read_context("sessions") or []
        for session in sessions:
            if session.get("state") == "running" or (
                session.get("state") == "completed" and not session.get("processed")
            ):
                self._refresh_session(session)

    def _refresh_session(self, session: dict[str, Any]) -> dict[str, Any]:
        pid = session.get("pid")
        
        # probe the os to see if this guy is still breathing
        alive = bool(pid and self._pid_exists(pid))
        output = self._read_log(session.get("log_path", ""))
        previous_state = session.get("state")

        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            for item in state.get("sessions", []):
                if item["id"] != session["id"]:
                    continue
                item["last_ping"] = time()
                item["output"] = output.strip()
                if not alive:
                    # mark it dead if it crashed or finished silently
                    item["state"] = "completed" if output else "error"
                break
            return state

        state = replace_state(mutate)
        if not alive and previous_state == "running":
            self.event_bus.publish(
                "PROCESS_OUTPUT",
                {
                    "source": "recovery_service",
                    "session_id": session["id"],
                    "output": output.strip(),
                    "returncode": 0 if output else 1,
                },
            )
        return next(item for item in state["sessions"] if item["id"] == session["id"])

    def _read_log(self, log_path: str) -> str:
        path = Path(log_path)
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def _pid_exists(self, pid: int) -> bool:
        # standard unix trick to check if a process is alive without killing it
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
