from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from src.models.task import AgentType, Task


@dataclass(slots=True)
class Session:
    # keeps track of what an agent is doing right now
    id: str
    name: str
    active_tasks: list[str]
    tool: AgentType
    started_at: float
    last_ping: float
    log_path: str
    state: Literal["idle", "running", "error", "completed"]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ContextSlice:
    # represents a slice of the codebase a tool has access to
    id: str
    owner: str
    files: list[str]
    memory: dict[str, Any]
    shared_with: list[str]
    version: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ContextSlice":
        return cls(**payload)


@dataclass(slots=True)
class OrchestratorState:
    # holds everything we need to run the orchestrator loop
    sessions: list[Session]
    tasks: list[Task]
    global_context: ContextSlice
    phase: str
    config: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sessions": [session.to_dict() for session in self.sessions],
            "tasks": [task.to_dict() for task in self.tasks],
            "global_context": self.global_context.to_dict(),
            "phase": self.phase,
            "config": self.config,
        }
