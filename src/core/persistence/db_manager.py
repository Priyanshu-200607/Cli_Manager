from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[3]
DB_PATH = ROOT / "data" / "persistence" / "orchestrator.db"
LEGACY_JSON_PATH = ROOT / "data" / "context" / "global_state.json"
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


class DBManager:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        # make sure the directory is there before we accidentally crash on connect
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._initialized = False

    def init_db(self, default_state_factory: Callable[[], dict[str, Any]]) -> None:
        with self.lock:
            if self._initialized and DB_PATH.exists():
                return
            with self._connect() as connection:
                connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
                row = connection.execute(
                    "SELECT value FROM state_store WHERE key = ?",
                    ("global_state",),
                ).fetchone()
                if row is None:
                    # we probably want to seed it if there's nothing in there yet
                    state = self._load_initial_state(default_state_factory)
                    connection.execute(
                        "INSERT INTO state_store(key, value) VALUES (?, ?)",
                        ("global_state", json.dumps(state)),
                    )
                    connection.commit()
            self._initialized = True

    def read_state(self, default_state_factory: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        self.init_db(default_state_factory)
        with self.lock, self._connect() as connection:
            row = connection.execute(
                "SELECT value FROM state_store WHERE key = ?",
                ("global_state",),
            ).fetchone()
        state = json.loads(row[0]) if row else default_state_factory()
        defaults = default_state_factory()
        for key, value in defaults.items():
            state.setdefault(key, value)
        return state

    def write_state(
        self,
        state: dict[str, Any],
        default_state_factory: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        self.init_db(default_state_factory)
        with self.lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO state_store(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("global_state", json.dumps(state)),
            )
            connection.commit()
        return state

    def read_file_locks(self) -> list[dict[str, Any]]:
        self.init_db(lambda: {})
        with self.lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT file_path, owner_id, slice_id, claimed_at FROM file_locks ORDER BY file_path"
            ).fetchall()
        return [
            {
                "file_path": row[0],
                "owner_id": row[1],
                "slice_id": row[2],
                "claimed_at": row[3],
            }
            for row in rows
        ]

    def read_task_dependencies(self) -> list[dict[str, Any]]:
        self.init_db(lambda: {})
        with self.lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT parent_task_id, child_task_id, dependency_type FROM task_dependencies "
                "ORDER BY child_task_id, parent_task_id"
            ).fetchall()
        return [
            {
                "parent_task_id": row[0],
                "child_task_id": row[1],
                "dependency_type": row[2],
            }
            for row in rows
        ]

    def set_task_dependencies(
        self,
        child_task_id: str,
        parent_task_ids: list[str],
        dependency_type: str = "blocks",
    ) -> None:
        self.init_db(lambda: {})
        with self.lock, self._connect() as connection:
            connection.execute(
                "DELETE FROM task_dependencies WHERE child_task_id = ?",
                (child_task_id,),
            )
            for parent_task_id in parent_task_ids:
                connection.execute(
                    "INSERT OR REPLACE INTO task_dependencies(parent_task_id, child_task_id, dependency_type) "
                    "VALUES (?, ?, ?)",
                    (parent_task_id, child_task_id, dependency_type),
                )
            connection.commit()

    def claim_file_locks(self, owner_id: str, slice_id: str, files: list[str], claimed_at: float) -> bool:
        self.init_db(lambda: {})
        with self.lock, self._connect() as connection:
            existing = connection.execute(
                "SELECT file_path, owner_id FROM file_locks WHERE file_path IN (%s)"
                % ",".join("?" for _ in files),
                files,
            ).fetchall() if files else []
            
            # fail if someone else already has their hands on these files
            conflicts = [row for row in existing if row[1] != owner_id]
            if conflicts:
                return False
                
            for file_path in files:
                connection.execute(
                    "INSERT INTO file_locks(file_path, owner_id, slice_id, claimed_at) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(file_path) DO UPDATE SET owner_id = excluded.owner_id, slice_id = excluded.slice_id, claimed_at = excluded.claimed_at",
                    (file_path, owner_id, slice_id, claimed_at),
                )
            connection.commit()
        return True

    def release_file_locks(self, owner_id: str) -> None:
        self.init_db(lambda: {})
        with self.lock, self._connect() as connection:
            connection.execute("DELETE FROM file_locks WHERE owner_id = ?", (owner_id,))
            connection.commit()

    def clear_file_locks(self) -> None:
        self.init_db(lambda: {})
        with self.lock, self._connect() as connection:
            connection.execute("DELETE FROM file_locks")
            connection.commit()

    def clear_task_dependencies(self) -> None:
        self.init_db(lambda: {})
        with self.lock, self._connect() as connection:
            connection.execute("DELETE FROM task_dependencies")
            connection.commit()

    def _load_initial_state(self, default_state_factory: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        # port over from the old json file if it exists, then we can ignore it
        if LEGACY_JSON_PATH.exists():
            return json.loads(LEGACY_JSON_PATH.read_text(encoding="utf-8"))
        return default_state_factory()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
