PRAGMA journal_mode = WAL;

-- stores all the random json blobs for the orchestrator context
CREATE TABLE IF NOT EXISTS state_store (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- keeps agents from stepping on each other's toes when editing
CREATE TABLE IF NOT EXISTS file_locks (
  file_path TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL,
  slice_id TEXT NOT NULL,
  claimed_at REAL NOT NULL
);

-- tracks the tree of tasks so we know what blocks what
CREATE TABLE IF NOT EXISTS task_dependencies (
  parent_task_id TEXT NOT NULL,
  child_task_id TEXT NOT NULL,
  dependency_type TEXT NOT NULL DEFAULT 'blocks',
  PRIMARY KEY (parent_task_id, child_task_id)
);
