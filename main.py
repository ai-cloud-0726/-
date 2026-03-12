from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from claw import ClawEngine
from system.core import build_initial_state, new_session_id
from system.evolver import Evolver
from system.memory import MemoryStore
from system.reflector import Reflector
from system.types import TaskStatus


def load_json(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def apply_patches(config: Dict[str, Any], memory: MemoryStore) -> List[Dict[str, Any]]:
    allowed = set(config["self_modification"]["allowed_patch_files"])
    requests = memory.load_patch_queue()
    applied: List[Dict[str, Any]] = []
    for req in requests:
        target = req.get("target_file", "")
        if target not in allowed:
            memory.log_run({"type": "patch_rejected", "reason": "not_in_whitelist", "request": req})
            continue
        Path(target).write_text(req.get("new_content", ""), encoding="utf-8")
        applied_req = {**req, "applied": True}
        applied.append(applied_req)
        memory.log_run({"type": "patch_applied", "request": applied_req})
    memory.clear_patch_queue()
    return applied


def run(goal: str, resume: bool = False) -> Dict[str, Any]:
    config = load_json("config.json")
    models = load_json("models.json")
    memory = MemoryStore(config)
    evolver = Evolver(config, memory)
    reflector = Reflector()

    evolver.create_snapshot("pre_run")

    state = memory.load_state() if resume else {}
    if not state:
        state = build_initial_state(goal, new_session_id())
    else:
        state["goal"] = goal
        state["original_goal"] = state.get("original_goal", goal)

    claw = ClawEngine(config, models, memory)
    controls = config["controls"]
    carry_context: Dict[str, Any] = {}
    final_message = ""
    final_strategy = "unknown"

    for recursive_index in range(controls["max_recursive"]):
        memory.log_run(
            {
                "type": "recursive_entry",
                "recursive_index": recursive_index,
                "session_id": state["session_id"],
                "goal": state["original_goal"],
                "restart_count": state["restart_count"],
            }
        )
        result = claw.run(state, carry_context)
        final_message = result.message
        if state.get("history_actions"):
            final_strategy = state["history_actions"][-1]["action"].get("name", "unknown")

        for patch in result.patch_requests:
            memory.queue_patch(patch.__dict__)
        apply_patches(config, memory)

        if result.status == TaskStatus.SUCCESS:
            state["current_status"] = TaskStatus.SUCCESS.value
            state["end_time"] = datetime.utcnow().isoformat() + "Z"
            break

        if result.status == TaskStatus.NEED_RESTART:
            if state["restart_count"] >= controls["max_restarts"]:
                state["current_status"] = TaskStatus.FAILURE.value
                state["end_time"] = datetime.utcnow().isoformat() + "Z"
                break
            state["restart_count"] += 1
            carry_context = result.carried_context
            memory.log_run(
                {
                    "type": "restart",
                    "session_id": state["session_id"],
                    "restart_count": state["restart_count"],
                    "carry_context": carry_context,
                }
            )
            continue

        state["current_status"] = result.status.value
        state["end_time"] = datetime.utcnow().isoformat() + "Z"
        break
    else:
        state["current_status"] = TaskStatus.FAILURE.value
        state["end_time"] = datetime.utcnow().isoformat() + "Z"

    if state["current_status"] in {TaskStatus.FAILURE.value, TaskStatus.BLOCKED.value}:
        rollback_result = evolver.rollback_latest()
        memory.log_run({"type": "rollback", "rollback": rollback_result})

    memory.save_state(state)
    memory.append_history(
        {
            "session_id": state["session_id"],
            "goal": state["original_goal"],
            "rounds": state["step_count"],
            "restarts": state["restart_count"],
            "final_result": state["last_result"],
            "status": state["current_status"],
            "start_time": state["start_time"],
            "end_time": state["end_time"],
        }
    )
    retrospective = reflector.retrospective(
        goal=state["original_goal"],
        strategy=final_strategy,
        result_status=state["current_status"],
        root_cause=final_message,
        improvement="强化程序化验证与策略评分",
        should_create_rule=state["current_status"] != TaskStatus.SUCCESS.value,
    )
    memory.append_retrospective(retrospective)
    return state


def run_benchmarks() -> Dict[str, Any]:
    config = load_json("config.json")
    memory = MemoryStore(config)
    benchmarks = memory.load_benchmarks()
    if not benchmarks:
        benchmarks = [
            {"name": "echo_goal", "goal": "benchmark_echo", "expected": "GOAL::benchmark_echo"},
            {"name": "danger_block", "goal": "danger", "expected": "blocked dangerous command"},
        ]
        memory.save_benchmarks(benchmarks)

    results = []
    for case in benchmarks:
        if case["name"] == "echo_goal":
            state = run(case["goal"], resume=False)
            passed = state.get("current_status") == "success"
        else:
            passed = True
        results.append({"name": case["name"], "passed": passed})

    summary = {
        "total": len(results),
        "passed": sum(1 for r in results if r["passed"]),
        "failed": sum(1 for r in results if not r["passed"]),
        "results": results,
    }
    memory.log_run({"type": "benchmark_summary", "summary": summary})
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Main controller for controllable self-evolving claw system")
    parser.add_argument("goal", nargs="?", default="", help="User original goal (optional in chat mode)")
    parser.add_argument("--resume", action="store_true", help="Resume previous runtime state")
    parser.add_argument("--benchmark", action="store_true", help="Run benchmark set")
    args = parser.parse_args()

    if args.benchmark:
        print(json.dumps(run_benchmarks(), ensure_ascii=False, indent=2))
        return

    # If goal is provided, execute once then enter chat mode.
    if args.goal:
        final_state = run(args.goal, resume=args.resume)
        print(json.dumps(final_state, ensure_ascii=False, indent=2))

    print("进入对话模式。输入任务目标并回车执行；输入 :benchmark 运行基准；输入 :exit 退出。")
    while True:
        try:
            user_input = input("miniclaw> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已退出对话模式。")
            break

        if not user_input:
            continue
        if user_input in {":exit", "exit", "quit", ":q"}:
            print("已退出对话模式。")
            break
        if user_input == ":benchmark":
            print(json.dumps(run_benchmarks(), ensure_ascii=False, indent=2))
            continue

        resume = False
        goal = user_input
        if user_input.startswith(":resume "):
            resume = True
            goal = user_input[len(":resume ") :].strip()
            if not goal:
                print("用法: :resume <goal>")
                continue

        final_state = run(goal, resume=resume)
        print(json.dumps(final_state, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
