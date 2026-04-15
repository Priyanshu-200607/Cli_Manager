from __future__ import annotations

import json
import uuid
from pathlib import Path
from time import time
from typing import Any

from src.core.context_store import read_context, replace_state
from src.core.persistence.db_manager import DBManager
from src.models.context import ContextSlice


ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = ROOT / "data" / "persistence" / "artifacts"


class ContextGateway:
    def __init__(self) -> None:
        # make sure the dir exists before we try dumping files in there
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        self.db = DBManager()

    def create_slice(self, task_id: str) -> ContextSlice:
        # spin up a fresh context slice for a new task
        slice_model = ContextSlice(
            id=str(uuid.uuid4()),
            owner=task_id,
            files=[],
            memory={},
            shared_with=[],
            version=0,
        )

        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            state["context_slices"] = state.get("context_slices", [])
            state["context_slices"].append(slice_model.to_dict())
            return state

        replace_state(mutate)
        return slice_model

    def commit_slice(self, slice_id: str, data: dict[str, Any]) -> ContextSlice:
        updated: ContextSlice | None = None

        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            nonlocal updated
            for item in state.get("context_slices", []):
                if item["id"] == slice_id:
                    # merge in the new memory instead of blowing it away
                    item["memory"].update(data)
                    files = data.get("files")
                    if files:
                        item["files"] = sorted(set(item.get("files", []) + files))
                    shared = data.get("shared_with")
                    if shared:
                        item["shared_with"] = sorted(set(item.get("shared_with", []) + shared))
                    item["version"] = int(item.get("version", 0)) + 1
                    updated = ContextSlice.from_dict(item)
                    break
            return state

        replace_state(mutate)
        if updated is None:
            raise KeyError(f"Unknown context slice: {slice_id}")
        return updated

    def resolve_conflicts(self, file_path: str) -> dict[str, str]:
        for lock in read_context("file_locks") or []:
            if lock["file_path"] == file_path:
                return {"status": "blocked", "file_path": file_path, "owner_id": lock["owner_id"]}
        return {"status": "clear", "file_path": file_path}

    def write_artifact(self, task_id: str, filename: str, payload: dict[str, Any]) -> str:
        # dump the payload to disk and hand back the path
        artifact_path = ARTIFACT_DIR / f"{task_id}_{filename}"
        artifact_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return str(artifact_path.relative_to(ROOT))

    def get_slice(self, slice_id: str) -> ContextSlice | None:
        for item in read_context("context_slices") or []:
            if item["id"] == slice_id:
                return ContextSlice.from_dict(item)
        return None

    def claim_files(self, owner_id: str, slice_id: str, files: list[str]) -> bool:
        claimed = self.db.claim_file_locks(owner_id, slice_id, files, time())
        if claimed:
            replace_state(lambda state: state)
        return claimed

    def release_files(self, owner_id: str) -> None:
        self.db.release_file_locks(owner_id)
        replace_state(lambda state: state)
