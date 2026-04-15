# CLI Manager

Phase 0 implements the Gemini handoff skeleton for a terminal-based AI orchestration system.

## Architecture

The system follows a layered approach to isolate visual representation from process orchestration and data persistence.

- `view_terminal`: TUI layout, active session rendering, input loop.
- `runtime_pool`: subprocess lifecycle management for agent commands.
- `event_bus`: internal publish/subscribe transport between runtime and TUI.
- `context_store_location`: `./data/context/global_state.json`

## Phase 0 Scope

- Spawn `gemini --version` and capture its output.
- Broadcast subprocess messages from the runtime to the TUI.
- Render an "Active Sessions" view that updates in real time.

## Not In Scope

- Task routing logic.
- Multi-file context merging.


Based on the "Ruthless Reality" comparison with agtx and the current state of cli_manager, here are the potential updates required to transform your prototype
  into a high-performance, professional-grade system.

  1. Infrastructure Overhaul (The "agtx" Standards)
   * Git Worktree Isolation: 
       * Current: Agents share the same folder and wait for file_locks.
       * Update: Automatically create a git worktree in .agtx/worktrees/<task_id> for every task.
       * Benefit: Real parallel execution. Agent A can't accidentally delete Agent B's files.
   * Tmux / PTY Integration:
       * Current: Read-only log viewer in the TUI.
       * Update: Run agents inside a tmux window or a Pseudo-terminal (PTY).
       * Benefit: "Human-in-the-Loop." You can press a key to "Join" the agent's session and type commands yourself if it gets stuck.

  2. Intelligence & Autonomy (Expanding your "Lead")
   * Multi-Agent Debate Service:
       * Current: One Gemini agent plans; one Gemini agent critiques.
       * Update: Spawn two planning agents. Let them "debate" the architecture, and have a third "Summarizer" agent create the final blueprint.json.
       * Benefit: Massive increase in code quality by catching edge cases before implementation begins.
   * Real Token/Cost Counting:
       * Current: Simulated "Fuel" increments.
       * Update: Integrate with the Gemini/OpenAI API usage endpoints to track real cents/tokens spent per task.
       * Benefit: Real-world "Budgeting." Set a task to stop if it costs more than $0.10.

  3. Standardization & Connectivity
   * Built-in MCP Server:
       * Current: Custom internal event bus.
       * Update: Expose the TaskEngine and ContextGateway via Model Context Protocol (MCP).
       * Benefit: You can point other tools (like Claude Desktop or Cursor) at your cli_manager board to manage your tasks.
   * Plugin Architecture (YAML/TOML):
       * Current: Hardcoded Python logic for Planning/Building.
       * Update: Define workflows in .agtx/plugins/custom.toml. Define which agent handles which phase and what artifacts it produces.
       * Benefit: You can share your "workflows" with others without them needing to edit your Python code.

  4. TUI & UX Refinement
   * Global Dashboard Mode:
       * Current: Monitors one project at a time.
       * Update: A "Fleet View" (cli-manager --global) that scans all folders on your machine for .agtx data.
       * Benefit: Manage 5 different repos from a single terminal window.
   * Interactive DAG Visualizer:
       * Current: A static tree in the TUI.
       * Update: Allow the user to "Select" nodes in the DAG to re-run specific failed branches or modify their descriptions mid-build.

  ---

  THE "NEXT PHASE" PRIORITY LIST
  If you are moving to Gemini now, here is the order of operations I recommend:

   1. Isolation (High Priority): Implement Git Worktrees. It is the single biggest difference between a "Script" and a "System."
   2. The Debate (Medium Priority): Leverage your superior logic by adding Adversarial Planning.
   3. The Handover (Medium Priority): Implement Tmux so you can actually "Talk" to your agents instead of just watching them.

  Final Action: Commit your current "Phase Evolution" code to Git now. Then, in the next session, give Gemini the PROJECT_STATE.md and tell it: "We have the
  brain; now build the body. Start with Git Worktree isolation."