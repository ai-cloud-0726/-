from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


class ModelClient:
    def __init__(self, models_path: str):
        self.models = json.loads(Path(models_path).read_text(encoding="utf-8"))
        self.default_model = self.models.get("default_model", "mock")

    def generate(self, prompt: str, context: Dict[str, Any]) -> Dict[str, Any]:
        # Offline-safe deterministic mock. Replace with real provider integration later.
        truncated = prompt[:120].replace("\n", " ")
        return {
            "model": self.default_model,
            "content": f"[mock-response] {truncated}",
            "context_echo": {k: str(v)[:120] for k, v in context.items()},
        }
