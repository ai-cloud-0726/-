from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List
from uuid import uuid4

from .types import PatchRequest


class Improver:
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def classify_capacity_gap(self, failed_reason: str) -> bool:
        keywords = ["not found", "missing", "能力", "unknown action", "unsupported"]
        reason_lower = failed_reason.lower()
        return any(k in reason_lower for k in keywords)

    def propose_patch_request(self, reason: str) -> PatchRequest:
        target = "prompts/planner_prompt.txt"
        content = "根据失败记忆避免重复方案，优先选择未尝试且低风险动作。\n"
        return PatchRequest(
            request_id=str(uuid4()),
            target_file=target,
            reason=f"能力不足触发提示词增强: {reason}",
            new_content=content,
        )

    def improvement_note(self, reason: str, tried: List[str]) -> str:
        return (
            f"改进请求: reason={reason}; "
            f"avoid={','.join(tried[-3:]) if tried else 'none'}; "
            f"at={datetime.utcnow().isoformat()}Z"
        )
