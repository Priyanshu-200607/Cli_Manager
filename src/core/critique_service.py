from __future__ import annotations

from src.models.critique import CritiqueResult
from src.models.task import Task


class CritiqueService:
    def review(self, target_task: Task, review_task: Task, session_output: str, fuel_cost: int) -> CritiqueResult:
        # grab the metadata so we know if we should force a failure
        metadata = target_task.metadata
        auto_fix_depth = int(metadata.get("auto_fix_depth", 0))
        
        # intentionally fail the first pass so we can test the autofix loop
        should_fail = metadata.get("kind") in {"building", "validation"} and auto_fix_depth == 0
        verdict = "fail" if should_fail else "pass"
        
        summary = (
            f"Review failed for {target_task.title}; generate an auto-fix task."
            if should_fail
            else f"Review passed for {target_task.title}."
        )
        return CritiqueResult(
            task_id=target_task.id,
            review_task_id=review_task.id,
            verdict=verdict,
            summary=summary,
            auto_fix_required=should_fail,
            fuel_cost=fuel_cost,
        )
