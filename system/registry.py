from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .memory import MemoryStore


class AbilityRegistry:
    def __init__(self, config: Dict[str, Any], memory: MemoryStore):
        self.config = config
        self.memory = memory
        self.abilities_dir = Path(config["paths"]["abilities_dir"])
        self.abilities_dir.mkdir(parents=True, exist_ok=True)

    def register(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        usage: str,
        example: str,
        code: str,
        source: str = "generated",
    ) -> Dict[str, Any]:
        records = self.memory.load_registry()
        file_path = self.abilities_dir / f"{name}.py"
        file_path.write_text(code, encoding="utf-8")
        record = {
            "name": name,
            "description": description,
            "version": "1.0.0",
            "type": "python",
            "source": source,
            "entrypoint": f"{file_path}:run",
            "input_schema": parameters,
            "usage": usage,
            "example": example,
            "file": str(file_path),
            "success_count": 0,
            "failure_count": 0,
            "success_rate": 0.0,
            "avg_duration_sec": 0.0,
            "recent_failures": [],
            "enabled": True,
            "tested": False,
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        records = [r for r in records if r.get("name") != name] + [record]
        self.memory.save_registry(records)
        return record

    def update_stats(self, name: str, ok: bool, duration_sec: float, failure_reason: str = "") -> None:
        records = self.memory.load_registry()
        for r in records:
            if r.get("name") == name:
                r["success_count"] = r.get("success_count", 0) + (1 if ok else 0)
                r["failure_count"] = r.get("failure_count", 0) + (0 if ok else 1)
                total = r["success_count"] + r["failure_count"]
                r["success_rate"] = r["success_count"] / total if total else 0.0
                prev_avg = float(r.get("avg_duration_sec", 0.0))
                r["avg_duration_sec"] = (prev_avg * (total - 1) + duration_sec) / total if total else duration_sec
                if not ok and failure_reason:
                    recent = r.get("recent_failures", [])
                    recent.append(failure_reason)
                    r["recent_failures"] = recent[-10:]
        self.memory.save_registry(records)

    def retire_low_quality(self) -> List[Dict[str, Any]]:
        controls = self.config["controls"]
        threshold = controls.get("retire_low_success_rate", 0.25)
        fail_streak = controls.get("retire_fail_streak", 5)
        kept, retired = [], []
        for r in self.memory.load_registry():
            recent_failures = len(r.get("recent_failures", []))
            if r.get("success_rate", 1.0) < threshold and recent_failures >= fail_streak:
                r["enabled"] = False
                retired.append(r)
            else:
                kept.append(r)
        archived = self.memory.load_archived_registry() + retired
        self.memory.save_archived_registry(archived)
        self.memory.save_registry(kept)
        return retired

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        for record in self.memory.load_registry():
            if record.get("name") == name and record.get("enabled", True):
                return record
        return None

    def list_all(self) -> List[Dict[str, Any]]:
        return self.memory.load_registry()
