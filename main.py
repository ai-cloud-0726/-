from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from agent_system.core.types import ClawInput, RuntimeState, TaskStatus
from agent_system.memory.storage import Storage
from claw import ClawEngine


def load_json(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def apply_patch_requests(
    patch_requests: List[Dict[str, Any]],
    config: Dict[str, Any],
    storage: Storage,
    session_id: str,
) -> List[Dict[str, Any]]:
    whitelist = set(config["patch"]["allowed_files"])
    applied = []
    queue = []

    for patch in patch_requests:
        queue.append(patch)
        target = patch.get("target", "")
        if target not in whitelist:
            applied.append({"target": target, "status": "rejected", "reason": "target not in whitelist"})
            continue

        applied.append({"target": target, "status": "accepted", "description": patch.get("description", "")})

    storage.write_patch_queue(session_id, queue)
    return applied


def run_task(goal: str, config: Dict[str, Any]) -> Dict[str, Any]:
    storage = Storage(config)
    engine = ClawEngine(config, storage)

    session_id = str(uuid.uuid4())
    start_time = datetime.utcnow().isoformat()

    state = RuntimeState(
        session_id=session_id,
        goal=goal,
        max_steps=config["limits"]["max_steps"],
        planned_steps=[
            "Clarify objective and constraints",
            "Attempt primary solution path",
            "Validate against user goal and expected output",
            "Produce final result with trace",
        ],
    )

    context: Dict[str, Any] = {"original_goal": goal, "session_level_context": []}
    error_memory = []
    final_output = None

    for recursion in range(config["limits"]["max_recursions"]):
        state.recursion_count = recursion
        for _ in range(config["limits"]["max_restarts"] + 1):
            claw_input = ClawInput(goal=goal, context=context, state=state, error_memory=error_memory)
            output = engine.run(claw_input)

            patch_results = apply_patch_requests(output.patch_requests, config, storage, session_id)
            for rec in output.steps:
                rec.patch_applied = patch_results[-1] if patch_results else None

            state = output.state
            error_memory = output.error_memory
            storage.write_runtime_state(session_id, asdict(state))
            storage.write_error_memory(session_id, error_memory)

            if output.status in (TaskStatus.SUCCESS, TaskStatus.FAILURE, TaskStatus.BLOCKED):
                final_output = output
                break

            if output.status == TaskStatus.RESTART_REQUIRED:
                if state.restart_count >= config["limits"]["max_restarts"]:
                    state.status = TaskStatus.BLOCKED
                    final_output = output
                    break
                state.restart_count += 1
                payload = output.restart_payload or {}
                goal = payload.get("goal", goal)
                context = payload.get("context", context)
                context["restart_payload"] = payload
                context["session_level_context"].append(
                    {
                        "restart": state.restart_count,
                        "commands": payload.get("commands", []),
                        "steps": payload.get("steps", []),
                    }
                )
                continue

        if final_output is not None:
            break

    end_time = datetime.utcnow().isoformat()
    final_status = state.status.value
    history_record = {
        "session_id": session_id,
        "goal": goal,
        "rounds": state.step_count,
        "restarts": state.restart_count,
        "final_result": final_status,
        "start_time": start_time,
        "end_time": end_time,
    }
    storage.append_history(history_record)

    return {
        "session_id": session_id,
        "status": final_status,
        "steps": state.step_count,
        "restarts": state.restart_count,
        "last_result": state.last_result,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Main controller for main+claw system")
    parser.add_argument("goal", type=str, help="User original goal")
    parser.add_argument("--config", default="config.json")
    args = parser.parse_args()

    config = load_json(args.config)
    result = run_task(args.goal, config)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
