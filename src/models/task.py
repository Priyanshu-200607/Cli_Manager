from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal


TaskStatus = Literal["pending", "in_progress", "blocked", "critique", "done", "failed"]
AgentType = Literal["gemini", "codex", "unassigned"]


@dataclass(slots=True)
class Task:
    # use slots here for a bit of a performance bump since we make a lot of these
    id: str
    title: str
    description: str
    status: TaskStatus
    assigned_tool: AgentType
    context_ref: str
    created_at: float
    updated_at: float
    completed_at: float | None
    phase: int
    output_ref: str
    # metadata can store anything extra we might need later on
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> "Task":
        # make sure we copy so we don't accidentally mutate the original payload
        payload = dict(payload)
        payload.setdefault("metadata", {})
        return cls(**payload)
