from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List


class Storage:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.paths = config["paths"]
        for key in (
            "logs_dir",
            "debug_dir",
            "temp_dir",
            "history_dir",
            "state_dir",
            "patch_dir",
            "ability_dir",
            "prompt_dir",
        ):
            Path(self.paths[key]).mkdir(parents=True, exist_ok=True)

    def _write_json(self, path: str, data: Any) -> None:
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _read_json(self, path: str, default: Any) -> Any:
        p = Path(path)
        if not p.exists():
            return default
        return json.loads(p.read_text(encoding="utf-8"))

    def append_jsonl(self, path: str, record: Dict[str, Any]) -> None:
        with Path(path).open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def write_runtime_state(self, session_id: str, state: Dict[str, Any]) -> None:
        self._write_json(f"{self.paths['state_dir']}/{session_id}_runtime_state.json", state)

    def write_error_memory(self, session_id: str, error_memory: Iterable[Any]) -> None:
        normalized: List[Dict[str, Any]] = []
        for item in error_memory:
            normalized.append(asdict(item) if hasattr(item, "__dataclass_fields__") else item)
        self._write_json(f"{self.paths['state_dir']}/{session_id}_error_memory.json", normalized)

    def write_patch_queue(self, session_id: str, patch_queue: List[Dict[str, Any]]) -> None:
        self._write_json(f"{self.paths['patch_dir']}/{session_id}_patch_queue.json", patch_queue)

    def append_history(self, history_record: Dict[str, Any]) -> None:
        history_file = f"{self.paths['history_dir']}/execution_history.jsonl"
        self.append_jsonl(history_file, history_record)

    def log_round(self, session_id: str, record: Dict[str, Any]) -> None:
        self.append_jsonl(f"{self.paths['logs_dir']}/{session_id}.log.jsonl", record)

    def debug_round(self, session_id: str, record: Dict[str, Any]) -> None:
        self.append_jsonl(f"{self.paths['debug_dir']}/{session_id}.debug.jsonl", record)

    def load_prompt_meta(self) -> Dict[str, Any]:
        return self._read_json(f"{self.paths['prompt_dir']}/prompt_meta.json", default={"version": 1, "history": []})

    def save_prompt_meta(self, meta: Dict[str, Any]) -> None:
        self._write_json(f"{self.paths['prompt_dir']}/prompt_meta.json", meta)

    def load_ability_registry(self) -> Dict[str, Any]:
        return self._read_json(f"{self.paths['ability_dir']}/ability_registry.json", default={"abilities": []})

    def save_ability_registry(self, registry: Dict[str, Any]) -> None:
        self._write_json(f"{self.paths['ability_dir']}/ability_registry.json", registry)
