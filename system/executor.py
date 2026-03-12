from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict

from .registry import AbilityRegistry
from .types import Action


class Executor:
    def __init__(self, config: Dict[str, Any], registry: AbilityRegistry):
        self.config = config
        self.registry = registry
        self.blacklist = config.get("dangerous_commands_blacklist", [])
        perms = config.get("permissions", {})
        self.default_level = perms.get("default_level", "L2")
        self.allowed_levels = set(perms.get("allow_levels", ["L1", "L2"]))
        self.levels = perms.get("levels", {})

    def run(self, action: Action) -> Dict[str, Any]:
        if action.kind == "command":
            return self._run_command(action.payload.get("command", ""))
        if action.kind == "use_ability":
            return self._run_ability(action.payload.get("name", ""))
        if action.kind == "temp_python":
            return self._run_temp_python(action.payload.get("code", ""), action.payload.get("name", "temp_task"))
        return {"ok": False, "output": "unknown action", "error_type": "ActionError"}

    def _check_level(self, required: str) -> bool:
        return required in self.allowed_levels

    def _run_command(self, command: str) -> Dict[str, Any]:
        if not self._check_level("L2"):
            return {"ok": False, "output": "permission denied for command", "error_type": "PermissionDenied"}
        if any(item in command for item in self.blacklist):
            return {"ok": False, "output": "blocked dangerous command", "error_type": "DangerousCommand"}
        try:
            result = subprocess.run(command, shell=True, check=False, capture_output=True, text=True)
            out = (result.stdout + "\n" + result.stderr).strip()
            return {"ok": result.returncode == 0, "output": out, "returncode": result.returncode}
        except Exception as exc:
            return {"ok": False, "output": str(exc), "error_type": type(exc).__name__}

    def _run_ability(self, name: str) -> Dict[str, Any]:
        ability = self.registry.get(name)
        if not ability:
            return {"ok": False, "output": f"ability '{name}' not found", "error_type": "AbilityMissing"}
        return {"ok": True, "output": f"ability located at {ability['file']}"}

    def _run_temp_python(self, code: str, name: str) -> Dict[str, Any]:
        if not self._check_level("L2"):
            return {"ok": False, "output": "permission denied for temp python", "error_type": "PermissionDenied"}
        temp_dir = Path(self.config["paths"]["temp_dir"])
        temp_dir.mkdir(parents=True, exist_ok=True)
        script = temp_dir / f"{name}.py"
        script.write_text(code, encoding="utf-8")
        return self._run_command(f"python {script}")
