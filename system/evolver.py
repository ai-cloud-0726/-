from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from .memory import MemoryStore


class Evolver:
    def __init__(self, config: Dict[str, Any], memory: MemoryStore):
        self.config = config
        self.memory = memory
        self.snapshots_dir = Path(config["paths"]["snapshots_dir"])

    def create_snapshot(self, label: str) -> Dict[str, Any]:
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        target = self.snapshots_dir / f"{ts}_{label}"
        target.mkdir(parents=True, exist_ok=True)
        for item in ["main.py", "claw.py", "system", "prompts", "config.json", "models.json"]:
            p = Path(item)
            if p.exists():
                dest = target / p.name
                if p.is_dir():
                    shutil.copytree(p, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(p, dest)
        meta = self.memory.load_version_meta()
        history = meta.get("history", [])
        history.append({"time": ts, "snapshot": str(target), "label": label})
        meta["history"] = history
        meta["latest_snapshot"] = str(target)
        self.memory.save_version_meta(meta)
        return {"snapshot": str(target), "time": ts}

    def rollback_latest(self) -> Dict[str, Any]:
        meta = self.memory.load_version_meta()
        snap = meta.get("latest_snapshot")
        if not snap:
            return {"ok": False, "reason": "no_snapshot"}
        source = Path(snap)
        if not source.exists():
            return {"ok": False, "reason": "snapshot_missing"}
        for item in ["main.py", "claw.py", "system", "prompts", "config.json", "models.json"]:
            src = source / Path(item).name
            dst = Path(item)
            if src.exists():
                if dst.exists():
                    if dst.is_dir():
                        shutil.rmtree(dst)
                    else:
                        dst.unlink()
                if src.is_dir():
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
        return {"ok": True, "snapshot": snap}
