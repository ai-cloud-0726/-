from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .memory import MemoryStore


class Dashboard:
    def __init__(self, config: Dict[str, Any], memory: MemoryStore, models_config: Dict[str, Any]):
        self.config = config
        self.memory = memory
        self.models_config = models_config

    def _read_jsonl(self, path_str: str) -> List[Dict[str, Any]]:
        path = Path(path_str)
        if not path.exists():
            return []
        rows: List[Dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows

    def build(self) -> Dict[str, Any]:
        state = self.memory.load_state()
        errors = self.memory.load_error_memory()
        tasks = self.memory.read_json("history_file", [])
        registry = self.memory.load_registry()
        archived = self.memory.load_archived_registry()

        active_profile = self.models_config.get("active_profile", "default")
        profiles = self.models_config.get("profiles", {})
        profile = profiles.get(active_profile, {}) if isinstance(profiles, dict) else {}
        model_paths = profile.get("paths", {}) if isinstance(profile, dict) else {}

        prompt_trace = self._read_jsonl(str(model_paths.get("prompt_trace_file", "runtime/model_prompt_trace.jsonl")))
        response_trace = self._read_jsonl(str(model_paths.get("response_trace_file", "runtime/model_response_trace.jsonl")))

        prompt_tokens = sum(int(item.get("prompt_tokens_est", 0)) for item in prompt_trace)
        response_tokens = sum(int(item.get("response_tokens_est", 0)) for item in response_trace)
        total_tokens = prompt_tokens + response_tokens

        dashboard = {
            "session_id": state.get("session_id", ""),
            "goal": state.get("original_goal", ""),
            "status": state.get("current_status", ""),
            "iteration_count": int(state.get("step_count", 0)),
            "restart_count": int(state.get("restart_count", 0)),
            "task_rounds": len(state.get("history_actions", [])),
            "total_tasks": len(tasks) if isinstance(tasks, list) else 0,
            "error_count": len(errors),
            "model": {
                "active_profile": active_profile,
                "model_name": profile.get("model", ""),
                "prompt_tokens_est": prompt_tokens,
                "response_tokens_est": response_tokens,
                "total_tokens_est": total_tokens,
                "prompt_trace_records": len(prompt_trace),
                "response_trace_records": len(response_trace),
            },
            "abilities": {
                "enabled_count": len(registry),
                "archived_count": len(archived),
            },
        }
        self.memory.write_json("dashboard_file", dashboard)
        self.memory.log_run({"type": "dashboard_update", "dashboard": dashboard})
        return dashboard
