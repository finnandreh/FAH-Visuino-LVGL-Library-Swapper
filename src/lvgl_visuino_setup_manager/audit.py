from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


class AuditRepository:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()

    def record(
        self,
        *,
        event: str,
        result: str,
        setup_id: str | None = None,
        setup_path: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entry = {
            "operationId": f"op_{uuid.uuid4().hex}",
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
            "event": event,
            "result": result,
            "setupId": setup_id,
            "setupPath": setup_path,
            "details": details or {},
        }
        encoded = json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n"
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
        return entry
