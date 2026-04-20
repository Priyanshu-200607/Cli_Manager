# CLI Manager

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![SQLite](https://img.shields.io/badge/SQLite-WAL%20Mode-003B57?style=flat-square&logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Rich TUI](https://img.shields.io/badge/TUI-Rich%20Framework-FF6E3C?style=flat-square)](https://github.com/Textualize/rich)
[![License](https://img.shields.io/badge/License-MIT-22C55E?style=flat-square)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Evolution%20Phase-8B5CF6?style=flat-square)]()

> **A terminal-native AI orchestration system that autonomously plans, builds, critiques, and self-heals code — powered by multiple AI agents and driven entirely from your terminal.**

---

## Why CLI Manager?

Most AI coding tools are wrappers. You paste a prompt, get code, and hope for the best.

CLI Manager is different. It's not a script that calls an API — it's an **orchestration engine** that thinks in tasks, reasons about dependencies, routes work to the right agent, and fixes its own mistakes without you lifting a finger.

| A Simple AI Script | CLI Manager |
|---|---|
| One agent, one prompt | Multi-agent pipeline with specialized roles |
| Linear execution | Dependency-aware DAG task graphs |
| You fix the bugs | Self-healing via autonomous Critique + Auto-Fix loop |
| No memory between runs | SQLite-backed persistence with WAL mode |
| You manage everything | Approval-gated autonomy with full observability |

If a build task fails review, CLI Manager doesn't stop and ask you what to do. It spawns a recursive **Auto-Fix task**, routes it back through the execution agent, and keeps iterating until the critique passes — or until you intervene. That's the difference between a tool and a system.

---

## Features

### 🖥️ Interactive Terminal UI (TUI)
Built with Python's `rich` library — no browser, no Electron, no overhead.

- **Kanban Board** — Live task cards across `Pending → In Progress → Done` columns
- **DAG Visualizer** — Interactive directed acyclic graph showing task dependencies, traversable in-terminal
- **Log Viewer** — Toggle real-time agent output inspection with `l`
- **Approval Gating** — Manual confirmation before any task executes; you stay in control

### 🧠 Autonomous Routing & Task DAGs
- Submit a single high-level planning prompt
- The **Planning Agent** (Gemini) decomposes it into a structured DAG of sub-tasks
- Each sub-task is automatically routed: planning tasks → Planning Agent, build/fix tasks → Execution Agent (Codex/Gemini)
- Dependencies are respected; nothing runs out of order

### 🔁 Critique & Self-Healing Loop
- Every completed build task is automatically reviewed by a **Critique Agent** (Gemini)
- If it fails review, an **Auto-Fix task** is recursively spawned and executed
- The loop continues until the critique passes — no human intervention required
- Full audit trail in the log viewer

### 💾 Robust Persistence
- SQLite database (`data/persistence/orchestrator.db`) with WAL mode enabled for concurrent reads during active execution
- Stores: task metadata, DAG structure, file locks, agent assignments, and simulated fuel/token tracking
- Survives restarts — background PIDs are tracked and reconciled on boot

### 👁️ Process Recovery & Workspace Watching
- Orchestrator tracks subprocess PIDs across sessions
- Watches the `src/` directory for filesystem changes
- Automatically triggers validation tasks when source files are modified

---

## Architecture

```
cli-manager/
├── src/
│   ├── tui/                        # Visual layer
│   │   ├── main_view.py            # Entry point; orchestrates all panels
│   │   ├── dag_graph.py            # Interactive DAG visualizer
│   │   ├── kanban.py               # Task board (Pending / In Progress / Done)
│   │   ├── log_viewer.py           # Toggleable agent output inspector
│   │   └── approval_modal.py       # Gating UI before task execution
│   │
│   └── core/                       # Orchestration & data layer
│       ├── task_engine.py          # Task lifecycle: create → route → execute → critique
│       ├── routing_service.py      # Decides: which agent handles which task type
│       ├── runtime_pool.py         # Subprocess lifecycle manager for agent commands
│       ├── event_bus.py            # Pub/Sub transport: background runtime ↔ TUI
│       └── persistence/
│           └── db_manager.py       # SQLite state, file locks, DAG tracking
│
└── data/
    └── persistence/
        ├── orchestrator.db         # Primary state database (WAL mode)
        └── artifacts/              # Agent outputs: blueprints, builds, critiques
```

### Agent Roles

| Agent | Model | Role |
|---|---|---|
| Planning Agent | Gemini | Decomposes high-level goals into task DAGs |
| Execution Agent | Codex / Gemini | Implements build and fix tasks |
| Critique Agent | Gemini | Reviews completed builds; triggers Auto-Fix on failure |

### Data Flow

```
User Input (n)
     │
     ▼
Planning Agent ──► Generates DAG of sub-tasks
     │
     ▼
Routing Service ──► Assigns each task to the right agent
     │
     ▼
Runtime Pool ──► Spawns subprocesses; streams output via Event Bus
     │
     ▼
TUI ──► Live updates on Kanban + Log Viewer
     │
     ▼
Critique Agent ──► Reviews build output
     │
  pass? ──► Done ✓
  fail? ──► Auto-Fix task spawned ──► loops back to Routing Service
```

---

## Getting Started

### Prerequisites

- Python 3.10+
- Gemini API key (set as `GEMINI_API_KEY` in your environment)
- Codex CLI configured (optional, for execution agent)

### Installation

```bash
git clone https://github.com/yourusername/cli-manager.git
cd cli-manager
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Run

```bash
.venv/bin/python src/tui/main_view.py
```

### Keybindings

| Key | Action |
|-----|--------|
| `n` | Create a new Planning Task |
| `a` | Approve the selected task for execution |
| `l` | Toggle the Log Viewer panel |
| `q` | Quit |

---

## Roadmap

### 🌿 Git Worktree Isolation
Replace file-lock-based conflict prevention with isolated Git worktrees per task. Each agent runs in its own branch-scoped workspace — enabling **true parallel execution** without file collisions. Merge strategies handled post-critique.

### 🗣️ Multi-Agent Debate Mode
Before any build begins, two Planning Agents debate the architecture. A third **Summarizer Agent** synthesizes the debate into a final blueprint. You approve the blueprint before execution starts. Better plans, fewer Auto-Fix loops.

### 🔌 Model Context Protocol (MCP) Integration
Expose the Task Engine via MCP so external tools — Claude Desktop, Cursor, Zed — can read and write to the CLI Manager board. Build from your IDE; orchestrate from your terminal.

### 💰 Real Token & Cost Tracking
Replace simulated "Fuel" with actual API cost accounting. Set per-task and per-session budget caps. The orchestrator pauses and requests approval when a task would exceed its budget.

### 🖥️ Tmux / PTY Integration
Run agents inside pseudo-terminals for full **Human-in-the-Loop** support. If an agent gets stuck, you can type directly into its terminal session. Full interactivity without breaking the orchestration loop.

---

## Contributing

Pull requests are welcome. For major changes, open an issue first to discuss what you'd like to change. Please ensure tests pass and the TUI remains functional after your changes.

---

## License

MIT — see [LICENSE](LICENSE) for details.