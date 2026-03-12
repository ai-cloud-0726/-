from __future__ import annotations

from typing import Any, Dict, List


class Planner:
    def next_action(self, goal: str, planned_steps: List[str], step_count: int, errors: List[Dict[str, Any]]) -> Dict[str, Any]:
        if step_count < len(planned_steps):
            action = planned_steps[step_count]
        else:
            action = f"Refine strategy for goal: {goal}"

        failed_methods = {e.get("method") for e in errors}
        if action in failed_methods:
            action = f"Alternative approach for: {goal} (avoid repeated failed method)"

        return {
            "action": action,
            "step_index": step_count,
            "goal": goal,
        }
