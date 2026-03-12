from __future__ import annotations

from typing import Any, Dict, List


class Improver:
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def detect_capability_gap(self, evaluation: Dict[str, Any], output: Dict[str, Any]) -> bool:
        text = output.get("output", "").lower()
        return (not evaluation.get("success")) and any(k in text for k in ["not implemented", "missing", "unsupported"])

    def suggest_improvement(
        self,
        goal: str,
        round_index: int,
        capability_gap: bool,
        patch_count: int,
    ) -> Dict[str, Any]:
        if capability_gap:
            if patch_count < self.config["limits"]["max_patch_per_task"]:
                return {
                    "type": "self_patch_request",
                    "reason": "capability gap detected",
                    "patch": {
                        "target": "agent_system/executor/executor.py",
                        "description": f"Add support required for goal: {goal}",
                    },
                }
            return {"type": "ability_generation", "reason": "patch limit reached"}

        if round_index % 2 == 1:
            return {"type": "prompt_update", "reason": "Improve instruction precision"}
        return {"type": "strategy_shift", "reason": "Try a different plan path"}

    def build_temp_code_request(self, goal: str) -> Dict[str, Any]:
        return {
            "type": "temp_code",
            "action": f"temp_py:print('temporary experiment for goal: {goal}')",
        }
