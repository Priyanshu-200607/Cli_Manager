from __future__ import annotations

import uuid

from src.models.dag import DAGNode, TaskDAG
from src.models.task import Task


class PlannerService:
    def build_blueprint(self, planning_task: Task, session_output: str) -> dict:
        # hardcode the initial dag for the prototype, we can make this dynamic later
        nodes = [
            DAGNode(
                id="build-core",
                title=f"Building: Core for {planning_task.title}",
                description="Implement the core orchestration slice from the approved plan.",
                target_files=[
                    "src/core/task_engine.py",
                    "src/core/planner_service.py",
                ],
            ),
            DAGNode(
                id="build-ui",
                title=f"Building: TUI for {planning_task.title}",
                description="Implement the TUI slice described in the approved plan.",
                target_files=[
                    "src/tui/main_view.py",
                    "src/tui/components/approval_modal.py",
                ],
                # make sure the core is built before the UI
                depends_on=["build-core"],
            ),
            DAGNode(
                id="build-validation",
                title=f"Building: Validation for {planning_task.title}",
                description="Implement the validation and watcher slice from the approved plan.",
                target_files=[
                    "src/core/workspace_watcher.py",
                    "src/models/dag.py",
                ],
                depends_on=["build-ui"],
            ),
        ]
        dag = TaskDAG(nodes=nodes)
        
        # package it all up into a neat blueprint
        return {
            "blueprint_id": str(uuid.uuid4()),
            "target_files": sorted({path for node in nodes for path in node.target_files}),
            "implementation_steps": [node.description for node in nodes],
            "validation_criteria": [
                "Manual blueprint approval is required before building tasks run.",
                "Dependency-ordered building tasks complete in sequence.",
                "Workspace changes trigger validation tasks.",
            ],
            "architectural_constraints": "Keep module boundaries from the Gemini handoff intact.",
            "source_task_id": planning_task.id,
            "gemini_output": session_output,
            "build_tasks": [node.to_dict() for node in nodes],
            "dag": dag.to_dict(),
        }
