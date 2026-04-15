from __future__ import annotations

from pathlib import Path

from rich.panel import Panel
from rich.text import Text


def render_log_viewer(session: dict | None) -> Panel:
    # bail early if we don't have an active session to look at
    if session is None:
        return Panel(Text("No session selected"), title="Log View", border_style="magenta")
        
    log_path = Path(session.get("log_path", ""))
    
    # safely try to read the log, fallback if it disappeared
    if log_path.exists():
        lines = log_path.read_text(encoding="utf-8").splitlines()
        # only grab the tail so we don't blow up the UI with a massive file
        body = "\n".join(lines[-20:]) or "(empty log)"
    else:
        body = "(log file missing)"
        
    return Panel(Text(body), title=f"Log View: {session['name']}", border_style="magenta")
