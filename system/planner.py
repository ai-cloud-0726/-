from __future__ import annotations

from typing import Any, Dict, List

from .types import Action


class Planner:
    def _score(self, success_rate: float, reusability: float, risk: float, cost: float) -> float:
        return success_rate * 40 + reusability * 25 - risk * 20 - cost * 15

    def _candidate_actions(self, goal: str, step_index: int) -> List[Dict[str, Any]]:
        return [
            {
                "action": Action(kind="command", name=f"step_{step_index}_echo", payload={"command": f"echo GOAL::{goal}"}),
                "method": "echo_goal",
                "score": self._score(0.8, 0.3, 0.1, 0.1),
            },
            {
                "action": Action(
                    kind="temp_python",
                    name=f"step_{step_index}_temp_py",
                    payload={"code": f"print('working on goal: {goal}')", "name": f"step_{step_index}"},
                ),
                "method": "temp_python_goal",
                "score": self._score(0.75, 0.5, 0.2, 0.2),
            },
        ]

    def next_action(
        self,
        goal: str,
        step_index: int,
        failed_methods: List[str],
        step_chain: List[str],
    ) -> Action:
        candidates = self._candidate_actions(goal, step_index)
        filtered = [c for c in candidates if c["method"] not in failed_methods]
        picked = max(filtered or candidates, key=lambda x: x["score"])
        step_chain.append(f"strategy={picked['method']} score={picked['score']:.2f}")
        return picked["action"]
