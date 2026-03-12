from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


class Verifier:
    """Programmatic first, semantic second."""

    def verify(self, goal: str, execution: Dict[str, Any], expected_artifacts: List[str] | None = None) -> Dict[str, Any]:
        checks: List[Dict[str, Any]] = []
        ok = bool(execution.get("ok", False))
        checks.append({"check": "returncode_ok", "passed": ok})

        output = str(execution.get("output", ""))
        goal_hit = goal in output
        checks.append({"check": "goal_in_output", "passed": goal_hit})

        json_valid = True
        if output.strip().startswith("{"):
            try:
                json.loads(output)
            except Exception:
                json_valid = False
        checks.append({"check": "json_valid_if_json_like", "passed": json_valid})

        artifacts_ok = True
        if expected_artifacts:
            artifacts_ok = all(Path(p).exists() for p in expected_artifacts)
        checks.append({"check": "artifacts_exist", "passed": artifacts_ok})

        passed = all(c["passed"] for c in checks if c["check"] != "goal_in_output") and (goal_hit or ok)
        return {
            "passed": passed,
            "checks": checks,
            "reason": "programmatic_verifier_pass" if passed else "programmatic_verifier_failed",
        }
