from __future__ import annotations

import json
import uuid
from time import time
from typing import Any

from src.core.context_store import read_context, replace_state
from src.core.context_gateway import ContextGateway, ROOT
from src.core.critique_service import CritiqueService
from src.core.event_bus import EventBus
from src.core.persistence.db_manager import DBManager
from src.core.planner_service import PlannerService
from src.core.routing_service import RoutingService
from src.models.task import Task, TaskStatus


class TaskEngine:
    def __init__(
        self,
        event_bus: EventBus,
        context_gateway: ContextGateway,
        routing_service: RoutingService,
        planner_service: PlannerService | None = None,
        critique_service: CritiqueService | None = None,
    ) -> None:
        self.event_bus = event_bus
        self.context_gateway = context_gateway
        self.routing_service = routing_service
        self.planner_service = planner_service or PlannerService()
        self.critique_service = critique_service or CritiqueService()
        self.db = DBManager()

    def create_task(self, params: dict[str, Any]) -> Task:
        title = str(params.get("title", "")).strip()
        description = str(params.get("description", "")).strip()
        if not title or not description:
            raise ValueError("Task title and description are required")

        phase = int(params.get("phase", 1))
        task_id = str(uuid.uuid4())
        context_slice = self.context_gateway.create_slice(task_id)
        metadata = dict(params.get("metadata", {}))
        assigned_tool = params.get("assigned_tool") or self.routing_service.determine_agent(
            f"{title} {description}"
        )
        self._seed_metadata(title, metadata)
        # block the task right away if it needs someone to sign off on it
        initial_status: TaskStatus = "blocked" if self._should_start_blocked(metadata) else "pending"
        now = time()
        task = Task(
            id=task_id,
            title=title,
            description=description,
            status=initial_status,
            assigned_tool=assigned_tool,
            context_ref=context_slice.id,
            created_at=now,
            updated_at=now,
            completed_at=None,
            phase=phase,
            output_ref="",
            metadata=metadata,
        )
        dependencies = list(params.get("dependencies", []))

        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            state["tasks"] = state.get("tasks", [])
            state["tasks"].append(task.to_dict())
            history = state.get("task_history", [])
            history.append(self._history_event(task.id, "created", {"assigned_tool": assigned_tool}))
            state["task_history"] = history
            return state

        replace_state(mutate)
        self.db.set_task_dependencies(task.id, dependencies)
        self.event_bus.publish(
            "TASK_UPDATE",
            {"source": "task_engine", "task_id": task.id, "status": task.status, "action": "created"},
        )
        return task

    def update_task(self, task_id: str, patch: dict[str, Any]) -> Task:
        updated: Task | None = None
        patch = dict(patch)
        patch["updated_at"] = time()
        if patch.get("status") == "done":
            patch["completed_at"] = time()

        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            nonlocal updated
            for item in state.get("tasks", []):
                if item["id"] == task_id:
                    item.update(patch)
                    updated = Task.from_dict(item)
                    state["task_history"] = state.get("task_history", [])
                    state["task_history"].append(
                        self._history_event(task_id, "updated", {"patch": patch})
                    )
                    break
            return state

        replace_state(mutate)
        if updated is None:
            raise KeyError(f"Unknown task: {task_id}")
        self.event_bus.publish(
            "TASK_UPDATE",
            {
                "source": "task_engine",
                "task_id": task_id,
                "status": updated.status,
                "action": "updated",
            },
        )
        return updated

    def transition_status(self, task_id: str, new_status: TaskStatus) -> Task:
        return self.update_task(task_id, {"status": new_status})

    def approve_blueprint(self, planning_task_id: str) -> Task:
        # unblock tasks that were waiting on this blueprint
        task = self._get_task(planning_task_id)
        if task.metadata.get("kind") != "planning" or not task.output_ref:
            raise ValueError("Selected task does not have an approvable blueprint")
        metadata = dict(task.metadata)
        metadata["blueprint_approved"] = True
        metadata["approved_at"] = time()
        updated = self.update_task(planning_task_id, {"metadata": metadata})
        self.event_bus.publish(
            "TASK_APPROVED",
            {"source": "task_engine", "task_id": planning_task_id, "artifact_ref": updated.output_ref},
        )
        return updated

    def get_next_runnable(self) -> Task | None:
        tasks = [Task.from_dict(item) for item in (read_context("tasks") or [])]
        for task in tasks:
            if task.status == "pending" and self._can_run(task):
                return task
        return None

    def reconcile(self, runtime_pool: Any) -> None:
        self._unblock_tasks()
        self._process_completed_sessions()
        self._dispatch_pending_tasks(runtime_pool)

    def _dispatch_pending_tasks(self, runtime_pool: Any) -> None:
        tasks = [Task.from_dict(item) for item in (read_context("tasks") or [])]
        sessions = read_context("sessions") or []
        tasks_with_sessions = {
            task_id
            for session in sessions
            for task_id in session.get("active_tasks", [])
        }
        for task in tasks:
            if task.status != "pending" or task.id in tasks_with_sessions or not self._can_run(task):
                continue
            if task.assigned_tool == "codex":
                # try to grab the files we need, skip if someone else has them locked
                if not self._claim_task_files(task):
                    self.update_task(task.id, {"status": "blocked"})
                    continue
            self.transition_status(task.id, "in_progress")
            runtime_pool.spawn_agent(
                task.assigned_tool,
                context_id=task.context_ref,
                task_id=task.id,
                task_title=task.title,
            )

    def _process_completed_sessions(self) -> None:
        sessions = read_context("sessions") or []
        for session in sessions:
            if session.get("processed") or session.get("state") not in {"completed", "error"}:
                continue
            task_ids = session.get("active_tasks", [])
            task_id = task_ids[0] if task_ids else None
            if task_id:
                self._finalize_task(task_id, session)
            self._mark_session_processed(session["id"])

    def _finalize_task(self, task_id: str, session: dict[str, Any]) -> None:
        task = self._get_task(task_id)
        if task.assigned_tool == "codex":
            self.context_gateway.release_files(task.id)
        if session["state"] == "error":
            self.update_task(task_id, {"status": "failed"})
            return

        if task.metadata.get("kind") == "planning":
            artifact_ref, build_specs = self._write_blueprint(task, session)
            self.update_task(task_id, {"status": "done", "output_ref": artifact_ref})
            self.context_gateway.commit_slice(
                task.context_ref,
                {"session_output": session.get("output", ""), "artifact_ref": artifact_ref},
            )
            artifact_path = str(ROOT / artifact_ref)
            if self.routing_service.validate_handoff(artifact_path):
                self._spawn_build_graph(task, artifact_ref, build_specs)
            return

        if task.metadata.get("kind") in {"building", "validation", "autofix"}:
            artifact_ref = self._write_build_output(task, session)
            self.update_task(task_id, {"status": "critique", "output_ref": artifact_ref})
            self.context_gateway.commit_slice(
                task.context_ref,
                {"session_output": session.get("output", ""), "artifact_ref": artifact_ref},
            )
            # automatically spin up a critique task to check the work
            self._spawn_critique_task(task, artifact_ref)
            return

        if task.metadata.get("kind") == "critique":
            self._complete_critique(task, session)
            return

        artifact_ref = self._write_build_output(task, session)
        self.update_task(task_id, {"status": "done", "output_ref": artifact_ref})

    def _write_blueprint(self, task: Task, session: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
        payload = self.planner_service.build_blueprint(task, session.get("output", ""))
        artifact_ref = self.context_gateway.write_artifact(task.id, "blueprint.json", payload)
        return artifact_ref, payload.get("build_tasks", [])

    def _write_build_output(self, task: Task, session: dict[str, Any]) -> str:
        slice_model = self.context_gateway.get_slice(task.context_ref)
        payload = {
            "task_id": task.id,
            "status": "built",
            "source_blueprint": (slice_model.memory.get("blueprint_ref") if slice_model else ""),
            "codex_output": session.get("output", ""),
        }
        return self.context_gateway.write_artifact(task.id, "build_output.json", payload)

    def _spawn_build_graph(self, planning_task: Task, artifact_ref: str, build_specs: list[dict[str, Any]]) -> None:
        task_by_node: dict[str, Task] = {}
        for build_spec in build_specs:
            build_task = self.create_task(
                {
                    "title": build_spec["title"],
                    "description": build_spec["description"],
                    "phase": planning_task.phase,
                    "assigned_tool": "codex",
                    "metadata": {
                        "kind": "building",
                        "approval_required": True,
                        "planning_task_id": planning_task.id,
                        "blueprint_ref": artifact_ref,
                        "node_id": build_spec["id"],
                        "auto_fix_depth": 0,
                    },
                }
            )
            task_by_node[build_spec["id"]] = build_task
            self.context_gateway.commit_slice(
                build_task.context_ref,
                {
                    "blueprint_ref": artifact_ref,
                    "source_task_id": planning_task.id,
                    "files": build_spec.get("target_files", []),
                },
            )
        for build_spec in build_specs:
            child_task = task_by_node[build_spec["id"]]
            parent_task_ids = [
                task_by_node[parent].id for parent in build_spec.get("depends_on", []) if parent in task_by_node
            ]
            self.db.set_task_dependencies(child_task.id, parent_task_ids)
            self.event_bus.publish(
                "TASK_HANDOFF",
                {
                    "source": "task_engine",
                    "task_id": planning_task.id,
                    "build_task_id": child_task.id,
                    "artifact_ref": artifact_ref,
                    "depends_on": parent_task_ids,
                },
            )

    def _spawn_critique_task(self, target_task: Task, artifact_ref: str) -> None:
        critique_task = self.create_task(
            {
                "title": f"Critique: {target_task.title}",
                "description": f"Review Codex output from {artifact_ref}",
                "phase": target_task.phase,
                "assigned_tool": "gemini",
                "metadata": {
                    "kind": "critique",
                    "target_task_id": target_task.id,
                    "blueprint_ref": target_task.metadata.get("blueprint_ref", ""),
                    "approval_required": False,
                },
                "dependencies": [target_task.id],
            }
        )
        self.context_gateway.commit_slice(
            critique_task.context_ref,
            {
                "review_target": target_task.id,
                "artifact_ref": artifact_ref,
            },
        )

    def _complete_critique(self, critique_task: Task, session: dict[str, Any]) -> None:
        target_task = self._get_task(critique_task.metadata["target_task_id"])
        fuel_cost = int(session.get("fuel", {}).get("total_cost", 0))
        result = self.critique_service.review(target_task, critique_task, session.get("output", ""), fuel_cost)
        critique_artifact = self.context_gateway.write_artifact(
            critique_task.id,
            "critique.json",
            result.to_dict(),
        )
        self.update_task(critique_task.id, {"status": "done", "output_ref": critique_artifact})
        if result.auto_fix_required:
            self.update_task(
                target_task.id,
                {
                    "status": "failed",
                    "metadata": {
                        **target_task.metadata,
                        "critique_verdict": result.verdict,
                        "critique_summary": result.summary,
                    },
                },
            )
            self._spawn_auto_fix_task(target_task, critique_task.id)
        else:
            self.update_task(
                target_task.id,
                {
                    "status": "done",
                    "metadata": {
                        **target_task.metadata,
                        "critique_verdict": result.verdict,
                        "critique_summary": result.summary,
                    },
                },
            )

    def _spawn_auto_fix_task(self, target_task: Task, critique_task_id: str) -> None:
        metadata = dict(target_task.metadata)
        auto_fix_depth = int(metadata.get("auto_fix_depth", 0)) + 1
        auto_fix = self.create_task(
            {
                "title": f"Auto-Fix: {target_task.title}",
                "description": f"Fix issues discovered in critique for {target_task.title}",
                "phase": target_task.phase,
                "assigned_tool": "codex",
                "metadata": {
                    **metadata,
                    "kind": "autofix",
                    "approval_required": False,
                    "source_task_id": target_task.id,
                    "critique_task_id": critique_task_id,
                    "auto_fix_depth": auto_fix_depth,
                },
                "dependencies": [critique_task_id],
            }
        )
        target_slice = self.context_gateway.get_slice(target_task.context_ref)
        self.context_gateway.commit_slice(
            auto_fix.context_ref,
            {
                "blueprint_ref": metadata.get("blueprint_ref", ""),
                "source_task_id": target_task.id,
                "files": target_slice.files if target_slice else [],
            },
        )

    def _get_task(self, task_id: str) -> Task:
        for item in read_context("tasks") or []:
            if item["id"] == task_id:
                return Task.from_dict(item)
        raise KeyError(f"Unknown task: {task_id}")

    def _can_run(self, task: Task) -> bool:
        if task.metadata.get("approval_required") and not self._approval_granted(task):
            return False
        return self._dependencies_satisfied(task.id)

    def _claim_task_files(self, task: Task) -> bool:
        slice_model = self.context_gateway.get_slice(task.context_ref)
        files = slice_model.files if slice_model else []
        if not files:
            return True
        return self.context_gateway.claim_files(task.id, task.context_ref, files)

    def _unblock_tasks(self) -> None:
        tasks = [Task.from_dict(item) for item in (read_context("tasks") or [])]
        for task in tasks:
            if task.status not in {"blocked", "failed"}:
                continue
            if task.metadata.get("kind") == "critique":
                continue
            slice_model = self.context_gateway.get_slice(task.context_ref)
            files = slice_model.files if slice_model else []
            if self._can_run(task) and all(
                self.context_gateway.resolve_conflicts(file_path)["status"] == "clear" for file_path in files
            ):
                self.transition_status(task.id, "pending")

    def _dependencies_satisfied(self, task_id: str) -> bool:
        current_task = self._get_task(task_id)
        dependencies = read_context("task_dependencies") or []
        parent_ids = [item["parent_task_id"] for item in dependencies if item["child_task_id"] == task_id]
        if not parent_ids:
            return True
        tasks = {item["id"]: item for item in (read_context("tasks") or [])}
        valid_parent_states = {"done"}
        if current_task.metadata.get("kind") == "critique":
            valid_parent_states.add("critique")
        return all(tasks.get(parent_id, {}).get("status") in valid_parent_states for parent_id in parent_ids)

    def _approval_granted(self, task: Task) -> bool:
        if not task.metadata.get("approval_required"):
            return True
        planning_task_id = task.metadata.get("planning_task_id")
        if not planning_task_id:
            return False
        planning_task = self._get_task(planning_task_id)
        return bool(planning_task.metadata.get("blueprint_approved"))

    def _should_start_blocked(self, metadata: dict[str, Any]) -> bool:
        return bool(metadata.get("approval_required"))

    def _seed_metadata(self, title: str, metadata: dict[str, Any]) -> None:
        normalized = title.lower()
        if normalized.startswith("planning:"):
            metadata.setdefault("kind", "planning")
            metadata.setdefault("blueprint_approved", False)
        elif normalized.startswith("building:"):
            metadata.setdefault("kind", "building")
            metadata.setdefault("approval_required", True)
            metadata.setdefault("auto_fix_depth", 0)
        elif normalized.startswith("validation:"):
            metadata.setdefault("kind", "validation")
            metadata.setdefault("approval_required", False)
            metadata.setdefault("auto_fix_depth", 0)
        elif normalized.startswith("critique:"):
            metadata.setdefault("kind", "critique")
            metadata.setdefault("approval_required", False)
        elif normalized.startswith("auto-fix:"):
            metadata.setdefault("kind", "autofix")
            metadata.setdefault("approval_required", False)
            metadata.setdefault("auto_fix_depth", 1)

    def _mark_session_processed(self, session_id: str) -> None:
        def mutate(state: dict[str, Any]) -> dict[str, Any]:
            for session in state.get("sessions", []):
                if session["id"] == session_id:
                    session["processed"] = True
                    break
            return state

        replace_state(mutate)

    def _history_event(self, task_id: str, action: str, details: dict[str, Any]) -> dict[str, Any]:
        return {
            "task_id": task_id,
            "action": action,
            "timestamp": time(),
            "details": details,
        }
