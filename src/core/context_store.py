from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from src.core.persistence.db_manager import DBManager, DB_PATH


ROOT = Path(__file__).resolve().parents[2]
STORE_PATH = DB_PATH
# grab a reentrant lock just in case we hit this from the same thread twice
_LOCK = threading.RLock()
_DB = DBManager()


def _default_state() -> dict[str, Any]:
    # fallback state if the db is totally empty
    return {
        "version": 0,
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
        "file_locks": [],
        "task_dependencies": [],
        "fuel_ledger": [],
    }


def _ensure_store() -> None:
    _DB.init_db(_default_state)


def lock_context(timeout: float = 5.0, poll_interval: float = 0.05) -> None:
    _ensure_store()
    _LOCK.acquire()


def unlock_context() -> None:
    try:
        _LOCK.release()
    except RuntimeError:
        # ignore it if we're not actually holding the lock
        pass


def _read_state() -> dict[str, Any]:
    _ensure_store()
    state = _DB.read_state(_default_state)
    state["file_locks"] = _DB.read_file_locks()
    state["task_dependencies"] = _DB.read_task_dependencies()
    return state


def _write_state(state: dict[str, Any]) -> dict[str, Any]:
    # bump the version so watchers know something changed
    state["version"] = int(state.get("version", 0)) + 1
    state.pop("file_locks", None)
    state.pop("task_dependencies", None)
    _DB.write_state(state, _default_state)
    state["file_locks"] = _DB.read_file_locks()
    state["task_dependencies"] = _DB.read_task_dependencies()
    return state


def read_context(key: str | None = None) -> Any:
    state = _read_state()
    if key is None:
        return state
    return state.get(key)


def write_context(key: str, value: Any) -> dict[str, Any]:
    lock_context()
    try:
        state = _read_state()
        state[key] = value
        return _write_state(state)
    finally:
        unlock_context()


def replace_state(mutator: Any) -> dict[str, Any]:
    lock_context()
    try:
        state = _read_state()
        next_state = mutator(state)
        return _write_state(next_state)
    finally:
        unlock_context()
