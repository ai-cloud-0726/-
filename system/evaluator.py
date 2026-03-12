from __future__ import annotations

from typing import Any, Dict

from .types import RoundEvaluation


class Evaluator:
    def evaluate(
        self,
        goal: str,
        action: Dict[str, Any],
        execution: Dict[str, Any],
        planned_ok: bool,
        verifier_result: Dict[str, Any],
    ) -> RoundEvaluation:
        if verifier_result.get("passed") and planned_ok and execution.get("ok", False):
            return RoundEvaluation(success=True, reason="程序化验证通过且符合步骤", next_step="结束任务")

        reason = verifier_result.get("reason", "结果未达成目标")
        if not planned_ok:
            reason = "执行偏离预定步骤"
        elif not execution.get("ok", False):
            reason = f"执行失败: {execution.get('error_type', 'UnknownError')}"

        need_restart = execution.get("error_type") in {"DangerousCommand", "ActionError", "PermissionDenied"}
        return RoundEvaluation(success=False, reason=reason, next_step="记录失败并尝试新方案", need_restart=need_restart)
