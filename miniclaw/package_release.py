#!/usr/bin/env python3
from __future__ import annotations

import json
import zipfile
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
DIST = BASE / "dist"
DIST.mkdir(exist_ok=True)

INCLUDE_FILES = [
    "main.py",
    "config.json",
    "apikey.json",
    "skll.json",
    "clock.json",
    "state.json",
    "wechat_inbox.txt",
    "wechat_outbox.txt",
    "test_main.py",
]

archive_name = DIST / f"miniclaw_release_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"

with zipfile.ZipFile(archive_name, "w", zipfile.ZIP_DEFLATED) as zf:
    for rel in INCLUDE_FILES:
        p = BASE / rel
        if p.exists():
            zf.write(p, arcname=f"miniclaw/{rel}")

    launcher = """#!/usr/bin/env bash
set -e
cd \"$(dirname \"$0\")/miniclaw\"
python3 main.py
"""
    zf.writestr("run_miniclaw.sh", launcher)

    meta = {
        "name": "miniclaw",
        "generated_at": datetime.now().isoformat(),
        "files": INCLUDE_FILES,
    }
    zf.writestr("PACKAGE_META.json", json.dumps(meta, ensure_ascii=False, indent=2))

print(archive_name)
