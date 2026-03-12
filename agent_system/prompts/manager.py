from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from agent_system.memory.storage import Storage


class PromptManager:
    def __init__(self, storage: Storage, config: Dict[str, Any]):
        self.storage = storage
        self.config = config
        self.prompt_file = Path(config["paths"]["prompt_dir"]) / "system_prompt.txt"
        if not self.prompt_file.exists():
            self.prompt_file.write_text("You are claw, execute safely and stay on user goal.", encoding="utf-8")

    def load_prompt(self) -> str:
        return self.prompt_file.read_text(encoding="utf-8")

    def update_prompt(self, new_prompt: str, reason: str) -> Dict[str, Any]:
        meta = self.storage.load_prompt_meta()
        max_updates = self.config["limits"]["max_prompt_updates_per_task"]
        if len(meta.get("history", [])) >= max_updates:
            return {"ok": False, "reason": "prompt update limit reached"}

        meta["version"] = int(meta.get("version", 1)) + 1
        entry = {
            "version": meta["version"],
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
        }
        meta.setdefault("history", []).append(entry)
        self.prompt_file.write_text(new_prompt, encoding="utf-8")
        self.storage.save_prompt_meta(meta)
        return {"ok": True, "meta": entry}
