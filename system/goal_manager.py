from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List


class GoalManager:
    def initialize(self, goal: str) -> Dict[str, Any]:
        now = datetime.utcnow().isoformat() + "Z"
        return {
            "main_goal": goal,
            "success_criteria": [
                "执行步骤可追踪",
                "结果满足用户目标",
                "失败后有改进并避免重复错误",
            ],
            "subgoals": [
                {"id": "g1", "name": "理解任务", "status": "done", "depends_on": [], "result": "已解析"},
                {"id": "g2", "name": "执行与验证", "status": "running", "depends_on": ["g1"], "result": ""},
            ],
            "current_blocker": "",
            "last_failure_reason": "",
            "next_action": "plan_next_step",
            "updated_at": now,
        }

    def touch(self, goal_state: Dict[str, Any], blocker: str, last_failure: str, next_action: str) -> Dict[str, Any]:
        goal_state["current_blocker"] = blocker
        goal_state["last_failure_reason"] = last_failure
        goal_state["next_action"] = next_action
        goal_state["updated_at"] = datetime.utcnow().isoformat() + "Z"
        return goal_state

    def mark_done(self, goal_state: Dict[str, Any], subgoal_id: str, result: str) -> Dict[str, Any]:
        subgoals: List[Dict[str, Any]] = goal_state.get("subgoals", [])
        for g in subgoals:
            if g.get("id") == subgoal_id:
                g["status"] = "done"
                g["result"] = result
        goal_state["updated_at"] = datetime.utcnow().isoformat() + "Z"
        return goal_state
