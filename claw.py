from __future__ import annotations

from datetime import datetime
from time import perf_counter
from typing import Any, Dict, List

from system.evaluator import Evaluator
from system.executor import Executor
from system.goal_manager import GoalManager
from system.improver import Improver
from system.memory import MemoryStore
from system.model import ModelClient
from system.planner import Planner
from system.prompts import PromptManager
from system.registry import AbilityRegistry
from system.types import ClawResult, ErrorRecord, PatchRequest, TaskStatus
from system.core import error_streak
from system.verifier import Verifier


class ClawEngine:
    def __init__(self, config: Dict[str, Any], models: Dict[str, Any], memory: MemoryStore):
        self.config = config
        self.memory = memory
        self.model = ModelClient(models)
        self.prompts = PromptManager(config, memory)
        self.registry = AbilityRegistry(config, memory)
        self.planner = Planner()
        self.executor = Executor(config, self.registry)
        self.evaluator = Evaluator()
        self.verifier = Verifier()
        self.improver = Improver(config)
        self.goal_manager = GoalManager()

    def run(self, state: Dict[str, Any], carry_context: Dict[str, Any]) -> ClawResult:
        controls = self.config["controls"]
        goal = state["original_goal"]
        tried_methods: List[str] = [e.get("failed_method", "") for e in self.memory.load_error_memory()]
        patch_requests: List[PatchRequest] = []
        step_chain: List[str] = carry_context.get("step_chain", [])

        goal_state = self.memory.load_goal_state() or self.goal_manager.initialize(goal)
        self.memory.save_goal_state(goal_state)

        for _ in range(controls["max_steps"]):
            step = state["step_count"] + 1
            action = self.planner.next_action(goal, step, tried_methods, step_chain)
            state["step_count"] = step

            model_note = self.model.generate(self.prompts.load("system_prompt"), {"goal": goal, "step": step})
            t0 = perf_counter()
            execution = self.executor.run(action)
            duration = perf_counter() - t0
            planned_ok = len(step_chain) > 0
            verifier_result = self.verifier.verify(goal, execution)
            evaluation = self.evaluator.evaluate(goal, action.__dict__, execution, planned_ok, verifier_result)

            error_record = None
            if not evaluation.success:
                error_record = ErrorRecord(
                    failed_method=action.name,
                    failed_reason=evaluation.reason,
                    error_type=execution.get("error_type", "EvaluationError"),
                    related_output=execution.get("output", ""),
                    round_index=step,
                    timestamp=datetime.utcnow().isoformat() + "Z",
                )
                tried_methods.append(error_record.failed_method)
                self.memory.add_error_memory(error_record.__dict__)
                goal_state = self.goal_manager.touch(goal_state, blocker=evaluation.reason, last_failure=evaluation.reason, next_action="replan")
                self.memory.save_goal_state(goal_state)

            improvement = self.improver.improvement_note(evaluation.reason, tried_methods)
            if error_record and self.improver.classify_capacity_gap(error_record.failed_reason):
                patch_requests.append(self.improver.propose_patch_request(error_record.failed_reason))

            self.memory.log_run(
                {
                    "type": "round",
                    "session_id": state["session_id"],
                    "goal": goal,
                    "action": action.__dict__,
                    "result": execution,
                    "evaluation": evaluation.__dict__,
                    "verifier": verifier_result,
                    "error": error_record.__dict__ if error_record else None,
                    "improvement_request": improvement,
                    "patch_applied": False,
                    "restart_info": {"restart_count": state["restart_count"]},
                }
            )
            self.memory.log_debug(
                {
                    "model_note": model_note,
                    "step_chain": step_chain,
                    "tried_methods": tried_methods[-10:],
                    "error_streak": error_streak(self.memory.load_error_memory()),
                    "goal_state": goal_state,
                }
            )

            self.registry.update_stats(action.name, execution.get("ok", False), duration, evaluation.reason if not evaluation.success else "")
            retired = self.registry.retire_low_quality()
            if retired:
                self.memory.log_run({"type": "ability_retire", "retired": retired})

            state["history_actions"].append(
                {
                    "round": step,
                    "action": action.__dict__,
                    "result": execution,
                    "evaluation": evaluation.__dict__,
                    "verifier": verifier_result,
                }
            )
            state["last_result"] = execution.get("output", "")
            state["current_status"] = TaskStatus.RUNNING.value
            self.memory.save_state(state)

            if evaluation.success:
                goal_state = self.goal_manager.mark_done(goal_state, "g2", "已完成执行与验证")
                self.memory.save_goal_state(goal_state)
                return ClawResult(
                    status=TaskStatus.SUCCESS,
                    message="任务成功",
                    rounds=step,
                    patch_requests=patch_requests,
                    carried_context={"step_chain": step_chain},
                    final_output=execution.get("output", ""),
                )

            if error_streak(self.memory.load_error_memory()) >= controls["max_same_error_streak"]:
                return ClawResult(
                    status=TaskStatus.NEED_RESTART,
                    message="重复同类错误过多，需要重启",
                    rounds=step,
                    patch_requests=patch_requests,
                    carried_context=self._carry_context(state),
                )

            if len(tried_methods) >= controls["max_failed_attempts"]:
                return ClawResult(
                    status=TaskStatus.FAILURE,
                    message="失败尝试次数超过限制",
                    rounds=step,
                    patch_requests=patch_requests,
                    carried_context=self._carry_context(state),
                )

            if len(patch_requests) >= controls["max_patch_attempts"]:
                return ClawResult(
                    status=TaskStatus.BLOCKED,
                    message="补丁请求次数超过限制",
                    rounds=step,
                    patch_requests=patch_requests,
                    carried_context=self._carry_context(state),
                )

        return ClawResult(
            status=TaskStatus.NEED_RESTART,
            message="达到最大步数，需要重启",
            rounds=state["step_count"],
            patch_requests=patch_requests,
            carried_context=self._carry_context(state),
        )

    def _carry_context(self, state: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "goal": state["goal"],
            "commands": [h["action"] for h in state.get("history_actions", [])],
            "steps": [h["round"] for h in state.get("history_actions", [])],
            "context": state.get("history_actions", []),
            "error_memory": self.memory.load_error_memory(),
            "step_chain": [
                f"round={h['round']} action={h['action'].get('name')}"
                for h in state.get("history_actions", [])
            ],
        }
