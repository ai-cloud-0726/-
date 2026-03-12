from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List


class Evaluator:
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def evaluate(
        self,
        goal: str,
        action: str,
        output: Dict[str, Any],
        planned_steps: List[str],
        round_index: int,
        error_memory: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        output_text = output.get("output", "")
        goal_aligned = goal.lower()[:20] in output_text.lower() or output.get("ok", False)
        step_aligned = round_index < len(planned_steps) and action == planned_steps[round_index] or action.startswith("Alternative")
        success = bool(output.get("ok")) and goal_aligned and step_aligned

        error_types = Counter(e.get("error_type", "other") for e in error_memory)
        repeated_error_hit = any(v >= self.config["limits"]["max_same_error_repeats"] for v in error_types.values())

        reason = "achieved" if success else "not achieved"
        next_step = "finish" if success else "try improved method"
        return {
            "success": success,
            "goal_aligned": goal_aligned,
            "step_aligned": step_aligned,
            "reason": reason,
            "next_suggestion": next_step,
            "repeated_error_hit": repeated_error_hit,
        }
