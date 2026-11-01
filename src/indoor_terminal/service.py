"""Resident-facing actions. Plugins own device communication."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from .events import EventStore
from .plugins import Host, discover


class OperationRejected(RuntimeError):
    pass


class IndoorTerminalService:
    def __init__(self, config, live=False):
        self.config = config
        self.live = live
        self.events = EventStore()
        self.host = Host(discover(config.get("plugins", ["demo"])), config.get("settings", {}),
                         live, self.events)
        self._lock = threading.RLock()
        self._started = None
        self._next_call = 0.0

    def start(self):
        with self._lock:
            self.host.start()
            self._started = datetime.now(timezone.utc).isoformat()

    def stop(self):
        with self._lock:
            self._started = None
            self.host.stop()

    def _call(self, capability):
        with self._lock:
            action = self.host.services.get(capability)
            if action is None:
                raise OperationRejected(f"unavailable: {capability}")
            result = action()
            self.events.add("operation", capability, data={"ok": bool(result.get("ok"))})
            return result

    def register(self):
        return self._call("station.register@1")

    def discover_center(self):
        return self._call("station.discover@1")

    def sync_rest(self):
        return self._call("content.sync@1")

    def call_elevator(self, confirmation):
        with self._lock:
            cfg = self.config.get("elevator", {})
            if not cfg.get("enabled", False) or not confirmation or confirmation != cfg.get("confirm_phrase", "CALL_ELEVATOR"):
                raise OperationRejected("呼梯未启用或口令不匹配")
            if time.monotonic() < self._next_call:
                raise OperationRejected("呼梯冷却中")
            if "elevator.call@1" not in self.host.services:
                raise OperationRejected("当前站点没有呼梯能力")
            self._next_call = time.monotonic() + max(0, float(cfg.get("cooldown_seconds", 30)))
            return self._call("elevator.call@1")

    def status(self):
        with self._lock:
            capabilities = sorted(key for key in self.host.services if not key.startswith("site."))
            return {
                "site_name": self.config.get("site_name", "室内机"), "mode": "live" if self.live else "dry-run",
                "started_at": self._started, "capabilities": capabilities,
                "event_sequence": self.events.latest_sequence,
                "elevator": {"enabled": bool(self.config.get("elevator", {}).get("enabled")) and "elevator.call@1" in capabilities,
                             "cooldown_remaining_seconds": round(max(0, self._next_call-time.monotonic()), 1),
                             "physical_dispatch_confirmed": False},
            }
