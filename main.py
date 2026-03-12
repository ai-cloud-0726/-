from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from claw import ClawEngine
from system.core import build_initial_state, new_session_id
from system.dashboard import Dashboard
from system.evolver import Evolver
from system.memory import MemoryStore
from system.model import ModelClient
from system.reflector import Reflector
from system.types import TaskStatus


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _feedback_print(msg: str) -> None:
    print(msg)


def load_json(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def check_model_connection() -> Dict[str, Any]:
    models = load_json("models.json")
    client = ModelClient(models)
    return client.check_connection()


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


def run(goal: str, resume: bool = False, feedback: bool = False) -> Dict[str, Any]:
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
        if feedback:
            _feedback_print(
                f"[main] 正在调用 claw (recursive={recursive_index + 1}/{controls['max_recursive']}, "
                f"restart={state['restart_count']}/{controls['max_restarts']})"
            )
        memory.log_run(
            {
                "type": "recursive_entry",
                "recursive_index": recursive_index,
                "session_id": state["session_id"],
                "goal": state["original_goal"],
                "restart_count": state["restart_count"],
            }
        )
        result = claw.run(state, carry_context, feedback=_feedback_print if feedback else None)
        final_message = result.message
        if state.get("history_actions"):
            final_strategy = state["history_actions"][-1]["action"].get("name", "unknown")

        for patch in result.patch_requests:
            memory.queue_patch(patch.__dict__)
        apply_patches(config, memory)

        if result.status == TaskStatus.SUCCESS:
            state["current_status"] = TaskStatus.SUCCESS.value
            state["end_time"] = _utc_now_iso()
            break

        if result.status == TaskStatus.NEED_RESTART:
            if state["restart_count"] >= controls["max_restarts"]:
                state["current_status"] = TaskStatus.FAILURE.value
                state["end_time"] = _utc_now_iso()
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
            if feedback:
                _feedback_print("[main] claw 返回需重启，已携带上下文准备下一次调用。")
            continue

        state["current_status"] = result.status.value
        state["end_time"] = _utc_now_iso()
        break
    else:
        state["current_status"] = TaskStatus.FAILURE.value
        state["end_time"] = _utc_now_iso()

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



def get_dashboard() -> Dict[str, Any]:
    config = load_json("config.json")
    models = load_json("models.json")
    memory = MemoryStore(config)
    dashboard = Dashboard(config, memory, models)
    return dashboard.build()


def _print_task_summary(state: Dict[str, Any], dashboard: Dict[str, Any], raw: bool = False) -> None:
    if raw:
        print(json.dumps(state, ensure_ascii=False, indent=2))
        print(json.dumps(dashboard, ensure_ascii=False, indent=2))
        return

    status = state.get("current_status", "unknown")
    goal = state.get("original_goal", "")
    result = state.get("last_result", "")
    rounds = state.get("step_count", 0)
    restarts = state.get("restart_count", 0)
    tokens = dashboard.get("model", {}).get("total_tokens_est", 0)
    print(f"[claw] 状态={status} | 目标={goal} | 轮数={rounds} | 重启={restarts} | token估算={tokens}")
    if result:
        print(f"[claw] 结果: {result}")

def main() -> None:
    parser = argparse.ArgumentParser(description="Main controller for controllable self-evolving claw system")
    parser.add_argument("goal", nargs="?", default="", help="User original goal (optional in chat mode)")
    parser.add_argument("--resume", action="store_true", help="Resume previous runtime state")
    parser.add_argument("--benchmark", action="store_true", help="Run benchmark set")
    parser.add_argument("--dashboard", action="store_true", help="Show runtime dashboard")
    args = parser.parse_args()

    if args.benchmark:
        print(json.dumps(run_benchmarks(), ensure_ascii=False, indent=2))
        return

    if args.dashboard:
        print(json.dumps(get_dashboard(), ensure_ascii=False, indent=2))
        return

    model_check = check_model_connection()
    if model_check.get("ok"):
        print(
            f"[model] 连接检查通过 | provider={model_check.get('provider')} "
            f"model={model_check.get('model')} | {model_check.get('detail')}"
        )
    else:
        print(
            f"[model] 连接检查失败 | provider={model_check.get('provider')} "
            f"model={model_check.get('model')} | {model_check.get('detail')}"
        )
        print("[model] 可继续使用 mock 或修复模型端点后重试。")

    raw_output = False

    # If goal is provided, execute once then enter chat mode.
    if args.goal:
        final_state = run(args.goal, resume=args.resume, feedback=True)
        _print_task_summary(final_state, get_dashboard(), raw=raw_output)

    print(
        "进入对话模式。输入任务目标并回车执行；输入 benchmark/:benchmark 运行基准；"
        "输入 dashboard/:dashboard 查看仪表盘；输入 json/:json 切换详细JSON输出；输入 exit/:exit 退出。"
    )
    while True:
        try:
            user_input = input("miniclaw> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已退出对话模式。")
            break

        if not user_input:
            continue
        cmd = user_input.lower()
        if cmd in {":exit", "exit", "quit", ":q"}:
            print("已退出对话模式。")
            break
        if cmd in {":benchmark", "benchmark"}:
            print(json.dumps(run_benchmarks(), ensure_ascii=False, indent=2))
            continue
        if cmd in {":dashboard", "dashboard"}:
            print(json.dumps(get_dashboard(), ensure_ascii=False, indent=2))
            continue
        if cmd in {":json", "json"}:
            raw_output = not raw_output
            print("详细JSON输出已开启。" if raw_output else "详细JSON输出已关闭。")
            continue

        resume = False
        goal = user_input
        if user_input.startswith(":resume "):
            resume = True
            goal = user_input[len(":resume ") :].strip()
            if not goal:
                print("用法: :resume <goal>")
                continue

        # interactive mode always gives execution-process feedback for each claw call
        final_state = run(goal, resume=resume, feedback=True)
        _print_task_summary(final_state, get_dashboard(), raw=raw_output)


if __name__ == "__main__":
    main()
