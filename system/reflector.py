from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict


class Reflector:
    def retrospective(
        self,
        goal: str,
        strategy: str,
        result_status: str,
        root_cause: str,
        improvement: str,
        should_create_rule: bool,
    ) -> Dict[str, Any]:
        return {
            "task": goal,
            "chosen_strategy": strategy,
            "result": result_status,
            "root_cause": root_cause,
            "improvement": improvement,
            "should_create_rule": should_create_rule,
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
