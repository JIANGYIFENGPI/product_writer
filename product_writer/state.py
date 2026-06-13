from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


_STATE_LOCK = threading.Lock()


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"titles": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def mark_title(path: Path, title: str, status: str, report_path: Path | None = None) -> None:
    with _STATE_LOCK:
        state = load_state(path)
        state.setdefault("titles", {})[title] = {
            "status": status,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "report_path": str(report_path) if report_path else None,
        }
        save_state(path, state)
