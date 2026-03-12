from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from .memory import MemoryStore


class PromptManager:
    def __init__(self, config: Dict[str, Any], memory: MemoryStore):
        self.config = config
        self.memory = memory
        self.prompts_dir = Path(config["paths"]["prompts_dir"])

    def load(self, name: str) -> str:
        path = self.prompts_dir / f"{name}.txt"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def update(self, name: str, new_text: str, reason: str) -> Dict[str, Any]:
        max_versions = self.config["self_modification"]["max_prompt_versions"]
        meta = self.memory.load_prompt_meta()
        versions = meta.get(name, [])
        if len(versions) >= max_versions:
            raise RuntimeError("Prompt version limit reached")

        path = self.prompts_dir / f"{name}.txt"
        old_text = path.read_text(encoding="utf-8") if path.exists() else ""
        path.write_text(new_text, encoding="utf-8")
        record = {
            "version": len(versions) + 1,
            "reason": reason,
            "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "old_length": len(old_text),
            "new_length": len(new_text),
        }
        versions.append(record)
        meta[name] = versions
        self.memory.update_prompt_meta(meta)
        return record
