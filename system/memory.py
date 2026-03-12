from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


DEFAULT_JSON_CONTENT = {
    "state_file": {},
    "goal_state_file": {},
    "error_memory_file": [],
    "patch_queue_file": [],
    "history_file": [],
    "retrospectives_file": [],
    "benchmarks_file": [],
    "ability_registry_file": [],
    "archived_ability_registry_file": [],
    "prompt_metadata_file": {},
    "version_meta_file": {"current_version": "0.0.0", "latest_snapshot": None, "history": []},
    "dashboard_file": {},
}



class MemoryStore:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.paths = config["paths"]
        self._ensure_files()

    def _ensure_files(self) -> None:
        for key, path_value in self.paths.items():
            path = Path(path_value)
            if key.endswith("_dir"):
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                if not path.exists():
                    if path.suffix == ".json":
                        content = DEFAULT_JSON_CONTENT.get(key, [])
                        path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
                    else:
                        path.write_text("", encoding="utf-8")

    def read_json(self, path_key: str, default: Any) -> Any:
        path = Path(self.paths[path_key])
        if not path.exists():
            return default
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return default
        return json.loads(text)

    def write_json(self, path_key: str, data: Any) -> None:
        path = Path(self.paths[path_key])
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def append_json_array(self, path_key: str, record: Dict[str, Any]) -> None:
        data = self.read_json(path_key, [])
        if not isinstance(data, list):
            data = []
        data.append(record)
        self.write_json(path_key, data)

    def log_run(self, payload: Dict[str, Any]) -> None:
        self._append_line(self.paths["run_log_file"], payload)

    def log_debug(self, payload: Dict[str, Any]) -> None:
        self._append_line(self.paths["debug_log_file"], payload)

    def _append_line(self, path_str: str, payload: Dict[str, Any]) -> None:
        payload = {"timestamp": _now_iso(), **payload}
        path = Path(path_str)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def save_state(self, state: Dict[str, Any]) -> None:
        self.write_json("state_file", state)

    def load_state(self) -> Dict[str, Any]:
        state = self.read_json("state_file", {})
        return state if isinstance(state, dict) else {}

    def save_goal_state(self, goal_state: Dict[str, Any]) -> None:
        self.write_json("goal_state_file", goal_state)

    def load_goal_state(self) -> Dict[str, Any]:
        data = self.read_json("goal_state_file", {})
        return data if isinstance(data, dict) else {}

    def add_error_memory(self, record: Dict[str, Any]) -> None:
        self.append_json_array("error_memory_file", record)

    def load_error_memory(self) -> List[Dict[str, Any]]:
        data = self.read_json("error_memory_file", [])
        return data if isinstance(data, list) else []

    def queue_patch(self, patch_record: Dict[str, Any]) -> None:
        self.append_json_array("patch_queue_file", patch_record)

    def load_patch_queue(self) -> List[Dict[str, Any]]:
        data = self.read_json("patch_queue_file", [])
        return data if isinstance(data, list) else []

    def clear_patch_queue(self) -> None:
        self.write_json("patch_queue_file", [])

    def append_history(self, task_record: Dict[str, Any]) -> None:
        self.append_json_array("history_file", task_record)

    def append_retrospective(self, record: Dict[str, Any]) -> None:
        self.append_json_array("retrospectives_file", record)

    def load_benchmarks(self) -> List[Dict[str, Any]]:
        data = self.read_json("benchmarks_file", [])
        return data if isinstance(data, list) else []

    def save_benchmarks(self, benchmarks: List[Dict[str, Any]]) -> None:
        self.write_json("benchmarks_file", benchmarks)

    def update_prompt_meta(self, meta: Dict[str, Any]) -> None:
        self.write_json("prompt_metadata_file", meta)

    def load_prompt_meta(self) -> Dict[str, Any]:
        data = self.read_json("prompt_metadata_file", {})
        return data if isinstance(data, dict) else {}

    def load_registry(self) -> List[Dict[str, Any]]:
        data = self.read_json("ability_registry_file", [])
        return data if isinstance(data, list) else []

    def save_registry(self, records: List[Dict[str, Any]]) -> None:
        self.write_json("ability_registry_file", records)

    def load_archived_registry(self) -> List[Dict[str, Any]]:
        data = self.read_json("archived_ability_registry_file", [])
        return data if isinstance(data, list) else []

    def save_archived_registry(self, records: List[Dict[str, Any]]) -> None:
        self.write_json("archived_ability_registry_file", records)

    def load_version_meta(self) -> Dict[str, Any]:
        data = self.read_json("version_meta_file", {})
        return data if isinstance(data, dict) else {}

    def save_version_meta(self, meta: Dict[str, Any]) -> None:
        self.write_json("version_meta_file", meta)

    def load_dashboard(self) -> Dict[str, Any]:
        data = self.read_json("dashboard_file", {})
        return data if isinstance(data, dict) else {}

    def save_dashboard(self, dashboard: Dict[str, Any]) -> None:
        self.write_json("dashboard_file", dashboard)

