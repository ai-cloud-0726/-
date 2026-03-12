from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from agent_system.memory.storage import Storage


class AbilityRegistry:
    def __init__(self, storage: Storage, config: Dict[str, Any]):
        self.storage = storage
        self.ability_dir = Path(config["paths"]["ability_dir"])

    def register_ability(
        self,
        name: str,
        description: str,
        params_format: Dict[str, Any],
        usage: str,
        example: str,
        code: str,
    ) -> Dict[str, Any]:
        registry = self.storage.load_ability_registry()
        ability_file = self.ability_dir / f"{name}.py"
        ability_file.write_text(code, encoding="utf-8")
        record = {
            "name": name,
            "description": description,
            "params_format": params_format,
            "usage": usage,
            "example": example,
            "file": str(ability_file),
        }
        registry.setdefault("abilities", []).append(record)
        self.storage.save_ability_registry(registry)
        return record

    def find(self, name: str) -> Optional[Dict[str, Any]]:
        registry = self.storage.load_ability_registry()
        for item in registry.get("abilities", []):
            if item["name"] == name:
                return item
        return None
