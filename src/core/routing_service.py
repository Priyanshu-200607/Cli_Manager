from __future__ import annotations

import json
from pathlib import Path

from src.models.task import AgentType


class RoutingService:
    # simple heuristic to figure out which agent should take the job
    GEMINI_KEYWORDS = ("design", "plan", "planning", "analyze", "architect", "structure", "blueprint", "critique", "review")
    CODEX_KEYWORDS = ("implement", "build", "building", "fix", "refactor", "test", "modify", "validation", "validate", "auto-fix")

    def determine_agent(self, task_description: str) -> AgentType:
        # just do a dumb string match for now, we can make it smarter later
        normalized = task_description.lower()
        if any(keyword in normalized for keyword in self.GEMINI_KEYWORDS):
            return "gemini"
        if any(keyword in normalized for keyword in self.CODEX_KEYWORDS):
            return "codex"
        
        # default to codex if we aren't sure
        return "codex"

    def validate_handoff(self, artifact_path: str) -> bool:
        # make sure the planning agent actually gave us what we need
        payload = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
        required = {
            "blueprint_id",
            "target_files",
            "implementation_steps",
            "validation_criteria",
            "architectural_constraints",
        }
        return required.issubset(payload.keys())
