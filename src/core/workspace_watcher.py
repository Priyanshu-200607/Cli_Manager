from __future__ import annotations

from pathlib import Path
from time import time

from src.core.context_store import read_context


class WorkspaceWatcher:
    def __init__(self, task_engine: object, root: Path) -> None:
        self.task_engine = task_engine
        self.root = root
        self.workspace_root = root / "src"
        self.snapshot: dict[str, float] = {}
        self.last_triggered: dict[str, float] = {}
        self.initialized = False

    def poll(self) -> None:
        current = self._scan()
        if not self.initialized:
            # grab the baseline on the first run so we don't trigger everything
            self.snapshot = current
            self.initialized = True
            return
            
        changed = [path for path, mtime in current.items() if self.snapshot.get(path) != mtime]
        self.snapshot = current
        
        for path in changed:
            if self._should_trigger(path):
                self.task_engine.create_task(
                    {
                        "title": f"Validation: {path}",
                        "description": f"Validate workspace change for {path}",
                        "phase": 1,
                        "assigned_tool": "codex",
                        "metadata": {
                            "kind": "validation",
                            "watched_file": path,
                            "approval_required": False,
                        },
                    }
                )
                self.last_triggered[path] = time()

    def _scan(self) -> dict[str, float]:
        snapshot: dict[str, float] = {}
        if not self.workspace_root.exists():
            return snapshot
            
        for path in self.workspace_root.rglob("*"):
            if not path.is_file():
                continue
            # skip all the junk we don't care about
            if any(part in {".venv", "__pycache__", "data"} for part in path.parts):
                continue
            snapshot[str(path.relative_to(self.root))] = path.stat().st_mtime
        return snapshot

    def _should_trigger(self, path: str) -> bool:
        # debounce rapid-fire events so we don't flood the queue
        recent = self.last_triggered.get(path, 0)
        if time() - recent < 1.0:
            return False
            
        tasks = read_context("tasks") or []
        for task in tasks:
            metadata = task.get("metadata", {})
            if (
                metadata.get("kind") == "validation"
                and metadata.get("watched_file") == path
                and task["status"] in {"pending", "in_progress", "blocked"}
            ):
                return False
        return True
