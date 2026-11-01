"""Thread-safe event journal exposed to the local dashboard."""

from __future__ import annotations

import copy
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Mapping, Optional


SENSITIVE_WORDS = ("password", "secret", "token", "credential", "template")


def redact(value: Any, key: str = "") -> Any:
    lowered = key.lower()
    if any(word in lowered for word in SENSITIVE_WORDS):
        return "***"
    if isinstance(value, Mapping):
        return {str(k): redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    if isinstance(value, str) and len(value) > 1024:
        return value[:1024] + "..."
    return copy.deepcopy(value)


class EventStore:
    def __init__(self, capacity: int = 500) -> None:
        self._events: Deque[Dict[str, Any]] = deque(maxlen=capacity)
        self._sequence = 0
        self._condition = threading.Condition()

    def add(
        self,
        kind: str,
        message: str,
        *,
        level: str = "info",
        data: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        with self._condition:
            self._sequence += 1
            event = {
                "sequence": self._sequence,
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "level": level,
                "kind": kind,
                "message": message,
                "data": redact(dict(data or {})),
            }
            self._events.append(event)
            self._condition.notify_all()
            return copy.deepcopy(event)

    def since(self, after: int = 0, limit: int = 200) -> List[Dict[str, Any]]:
        with self._condition:
            selected = [event for event in self._events if event["sequence"] > after]
            return copy.deepcopy(selected[-max(1, min(limit, 500)) :])

    @property
    def latest_sequence(self) -> int:
        with self._condition:
            return self._sequence
