from __future__ import annotations

from typing import Any, Dict


class ModelClient:
    """Unified LLM call wrapper. Uses deterministic mock behavior by default."""

    def __init__(self, models_config: Dict[str, Any]):
        self.models_config = models_config
        self.default = models_config.get("default", {})

    def generate(self, prompt: str, context: Dict[str, Any]) -> str:
        goal = context.get("goal", "")
        step = context.get("step", "")
        return (
            f"[model:{self.default.get('model', 'unknown')}] "
            f"goal={goal} | step={step} | advice=保持目标一致并执行可验证动作"
        )
