from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


class Executor:
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def execute(self, action: str, context: Dict[str, Any]) -> Dict[str, Any]:
        if action.startswith("cmd:"):
            command = action.replace("cmd:", "", 1).strip()
            return self._run_command(command)

        if action.startswith("temp_py:"):
            code = action.replace("temp_py:", "", 1)
            return self._run_temp_python(code)

        return {
            "ok": True,
            "type": "text",
            "output": f"Executed abstract action: {action}",
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _run_command(self, command: str) -> Dict[str, Any]:
        for banned in self.config["dangerous_commands_blacklist"]:
            if banned in command:
                return {"ok": False, "type": "command", "output": f"blocked dangerous command: {command}"}

        proc = subprocess.run(command, shell=True, capture_output=True, text=True)
        return {
            "ok": proc.returncode == 0,
            "type": "command",
            "output": proc.stdout + proc.stderr,
            "returncode": proc.returncode,
        }

    def _run_temp_python(self, code: str) -> Dict[str, Any]:
        temp_dir = Path(self.config["paths"]["temp_dir"])
        temp_dir.mkdir(parents=True, exist_ok=True)
        script = temp_dir / f"temp_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}.py"
        script.write_text(code, encoding="utf-8")
        proc = subprocess.run(f"python {script}", shell=True, capture_output=True, text=True)
        return {
            "ok": proc.returncode == 0,
            "type": "temp_python",
            "script": str(script),
            "output": proc.stdout + proc.stderr,
            "returncode": proc.returncode,
        }
