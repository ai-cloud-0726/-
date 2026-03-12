from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List

from agent_system.core.types import ClawInput, ClawOutput, ErrorMemoryEntry, ErrorType, StepRecord, TaskStatus
from agent_system.evaluator.evaluator import Evaluator
from agent_system.executor.executor import Executor
from agent_system.improver.improver import Improver
from agent_system.model.client import ModelClient
from agent_system.planner.planner import Planner
from agent_system.prompts.manager import PromptManager
from agent_system.registry.ability_registry import AbilityRegistry
from agent_system.memory.storage import Storage


class ClawEngine:
    def __init__(self, config: Dict[str, Any], storage: Storage):
        self.config = config
        self.storage = storage
        self.model = ModelClient(config["models_file"])
        self.planner = Planner()
        self.executor = Executor(config)
        self.evaluator = Evaluator(config)
        self.improver = Improver(config)
        self.prompts = PromptManager(storage, config)
        self.registry = AbilityRegistry(storage, config)

    def run(self, claw_input: ClawInput) -> ClawOutput:
        state = claw_input.state
        goal = claw_input.goal
        session_id = state.session_id
        errors: List[ErrorMemoryEntry] = list(claw_input.error_memory)
        step_records: List[StepRecord] = []
        patch_requests: List[Dict[str, Any]] = []
        same_error_count: Dict[str, int] = {}

        while state.step_count < state.max_steps:
            plan = self.planner.next_action(goal, state.planned_steps, state.step_count, [asdict(e) for e in errors])
            prompt = self.prompts.load_prompt()
            model_response = self.model.generate(prompt, {"goal": goal, "plan": plan})

            action = plan["action"]
            result = self.executor.execute(action, claw_input.context)
            state.command_history.append(action)

            evaluation = self.evaluator.evaluate(
                goal=goal,
                action=action,
                output=result,
                planned_steps=state.planned_steps,
                round_index=state.step_count,
                error_memory=[asdict(e) for e in errors],
            )

            improvement_request = None
            if not evaluation["success"]:
                err_type = ErrorType.COMMAND if result.get("type") == "command" else ErrorType.OTHER
                method = action
                err = ErrorMemoryEntry(
                    method=method,
                    reason=evaluation["reason"],
                    error_type=err_type,
                    related_output=result.get("output", ""),
                    round_index=state.step_count,
                )
                errors.append(err)
                key = f"{err.error_type}:{err.reason}"
                same_error_count[key] = same_error_count.get(key, 0) + 1

                capability_gap = self.improver.detect_capability_gap(evaluation, result)
                improvement_request = self.improver.suggest_improvement(goal, state.step_count, capability_gap, len(patch_requests))
                if improvement_request["type"] == "self_patch_request":
                    patch_requests.append(improvement_request["patch"])
                elif improvement_request["type"] == "prompt_update":
                    self.prompts.update_prompt(
                        self.prompts.load_prompt() + "\n- Keep stronger alignment with original goal.",
                        reason=improvement_request["reason"],
                    )
                elif capability_gap:
                    temp_req = self.improver.build_temp_code_request(goal)
                    temp_result = self.executor.execute(temp_req["action"], claw_input.context)
                    result["output"] += f"\n[capability-extension] {temp_result.get('output', '')}"

                if same_error_count[key] >= self.config["limits"]["max_same_error_repeats"]:
                    state.status = TaskStatus.BLOCKED
                    break

            step_record = StepRecord(
                round_index=state.step_count,
                goal=goal,
                action=action,
                result=result.get("output", ""),
                evaluation=evaluation,
                errors=[errors[-1]] if (errors and not evaluation["success"]) else [],
                improvement_request=improvement_request,
            )
            step_records.append(step_record)
            self.storage.log_round(session_id, asdict(step_record))
            self.storage.debug_round(
                session_id,
                {
                    "plan": plan,
                    "model_response": model_response,
                    "raw_result": result,
                    "evaluation": evaluation,
                },
            )

            state.history_actions.append({"round": state.step_count, "action": action, "ok": result.get("ok", False)})
            state.last_result = result.get("output", "")
            state.step_count += 1

            if evaluation["success"]:
                state.status = TaskStatus.SUCCESS
                break

            if len(errors) >= self.config["limits"]["max_fail_attempts_per_task"]:
                state.status = TaskStatus.RESTART_REQUIRED
                break

            if len(patch_requests) >= self.config["limits"]["max_patch_per_task"]:
                state.status = TaskStatus.RESTART_REQUIRED
                break

        if state.status == TaskStatus.RUNNING:
            state.status = TaskStatus.FAILURE

        restart_payload = None
        if state.status == TaskStatus.RESTART_REQUIRED:
            restart_payload = {
                "goal": goal,
                "commands": state.command_history,
                "steps": state.planned_steps,
                "context": claw_input.context,
                "error_memory": [asdict(e) for e in errors],
            }

        return ClawOutput(
            status=state.status,
            state=state,
            steps=step_records,
            patch_requests=patch_requests,
            error_memory=errors,
            restart_payload=restart_payload,
        )
