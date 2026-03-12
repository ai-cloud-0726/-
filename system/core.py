from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any, Dict, List
from uuid import uuid4


def new_session_id() -> str:
    return str(uuid4())


def build_initial_state(goal: str, session_id: str) -> Dict[str, Any]:
    now = datetime.utcnow().isoformat() + "Z"
    return {
        "session_id": session_id,
        "goal": goal,
        "original_goal": goal,
        "step_count": 0,
        "restart_count": 0,
        "history_actions": [],
        "last_result": "",
        "current_status": "running",
        "start_time": now,
        "end_time": None,
    }


def error_streak(errors: List[Dict[str, Any]]) -> int:
    if not errors:
        return 0
    last = errors[-1].get("error_type")
    streak = 0
    for e in reversed(errors):
        if e.get("error_type") == last:
            streak += 1
        else:
            break
    return streak


def summarize_errors(errors: List[Dict[str, Any]]) -> Dict[str, int]:
    counter = Counter(e.get("error_type", "Unknown") for e in errors)
    return dict(counter)
