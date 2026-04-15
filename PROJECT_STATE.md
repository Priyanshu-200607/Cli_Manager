# CLI-MANAGER: PROJECT STATE & HANDOVER

This document summarizes the current progress of the CLI AI Orchestration System for future agents (Gemini/Codex).

---

## 1. PROJECT STATUS: EVOLUTION PHASE
The system is **fully runnable** and provides a functional TUI interface for managing AI-driven tasks.

- **Interface**: A Rich-based TUI (`src/tui/main_view.py`) featuring:
    - **Kanban Board**: 3 lanes (Pending, In Progress, Done).
    - **DAG Graph**: Real-time tree visualization of task dependencies.
    - **Log Viewer**: Toggleable view (`l` to enter, `b` to return) for inspecting agent output.
    - **Approval Gating**: Planning outputs must be approved (`a` key) before execution.
- **Backend**: SQLite-backed persistence with WAL enabled (`data/persistence/orchestrator.db`).
- **Agents**: Supports `gemini` and `codex` CLIs. Requires these to be in the system PATH.

---

## 2. CORE FEATURES COMPLETED
- **Autonomous Routing**: Keywords like "plan" route to Gemini; "build" routes to Codex.
- **Task DAGs**: A single planning task generates a Directed Acyclic Graph of sub-tasks.
- **Critique & Self-Healing**: Completed Codex tasks are reviewed by Gemini. If they fail review, an "Auto-Fix" task is recursively generated.
- **Process Recovery**: The orchestrator can restart without losing track of background processes (uses PID-based recovery).
- **Workspace Watching**: Filesystem changes in `src/` trigger validation tasks.
- **Resource Management**: Simulated "Fuel" tracking (tokens/cost) is persisted for all agent runs.

---

## 3. DATA ARCHITECTURE
- **Persistence**: `src/core/persistence/db_manager.py` manages SQLite tables:
    - `state_store`: Global K/V for JSON-serialized state.
    - `file_locks`: Enforces single-agent ownership of source files.
    - `task_dependencies`: Tracks the DAG structure.
- **Models**: Defined in `src/models/`:
    - `Task`: Metadata, status, metadata-blobs (approvals, fuel).
    - `DAGNode`: Structure for fanned-out planning.
    - `CritiqueResult`: Verdicts (Pass/Fail) and Auto-Fix requirements.

---

## 4. REDUNDANT ARTIFACTS
- `data/context/global_state.json`: **REDUNDANT**. Migrated to SQLite.
- `data/context/artifacts/`: These are old MVP artifacts. Current artifacts live in `data/persistence/artifacts/`.
- `tests/*_smoke.py`: Useful for regression, but may need consolidation for production.

---

## 5. NEXT STEPS (FUTURE AGENT INSTRUCTIONS)
- **Integration**: Transition from simulated "Fuel" to real token counting if APIs are available.
- **Conflict Resolution**: Enhance `ContextGateway` to handle automatic merging of concurrent file edits.
- **Collaborative Intelligence**: Implement a "Debate" mode where multiple Gemini agents critique a plan *before* it reaches the user for approval.

---

## 6. HOW TO RUN
```bash
# Start the Orchestrator
.venv/bin/python src/tui/main_view.py

# Commands in TUI:
# n: Create new Planning Task
# a: Approve selected Task
# l: Toggle Log Viewer
# q: Quit
```
