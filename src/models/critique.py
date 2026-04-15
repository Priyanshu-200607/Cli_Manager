from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(slots=True)
class CritiqueResult:
    # basic structure for when an agent reviews another agent's work
    task_id: str
    review_task_id: str
    verdict: str
    summary: str
    # if it's really bad, we need to spin up a fix task
    auto_fix_required: bool
    fuel_cost: int

    def to_dict(self) -> dict:
        # just a helper to serialize easily
        return asdict(self)
