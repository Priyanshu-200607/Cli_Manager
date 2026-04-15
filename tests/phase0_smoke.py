from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.context_store import STORE_PATH, read_context, write_context
from src.core.event_bus import EventBus
from src.core.runtime_pool import RuntimePool


def wait_for_completion(timeout: float = 10.0) -> dict:
    # poll the context store until the agent finishes or we timeout
    deadline = time.time() + timeout
    while time.time() < deadline:
        sessions = read_context("sessions") or []
        if sessions and sessions[-1]["state"] in {"completed", "error"}:
            return sessions[-1]
        time.sleep(0.1)
    raise TimeoutError("Timed out waiting for gemini process to finish")


def main() -> int:
    # clean slate for the test run
    write_context("sessions", [])
    write_context("events", [])

    bus = EventBus()
    received: list[dict] = []
    bus.subscribe("PROCESS_OUTPUT", received.append)

    runtime = RuntimePool(bus)
    session_id = runtime.spawn_agent("gemini")
    assert session_id

    # wait for the fake gemini process to exit
    session = wait_for_completion()
    assert session["id"] == session_id
    assert session["state"] == "completed"
    assert session["output"]
    assert any(char.isdigit() for char in session["output"]), session["output"]
    assert received, "event bus did not receive subprocess output"

    payload = json.loads(STORE_PATH.read_text(encoding="utf-8"))
    assert payload["version"] >= 3
    assert payload["events"], "context store missing events"
    print("phase0_smoke: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
