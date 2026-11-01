"""Versioned service contracts, scoped events and installed plugin discovery."""
from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
from graphlib import CycleError, TopologicalSorter
from importlib import metadata
from threading import RLock
from typing import Any, Callable, Mapping

from .events import EventStore

GROUP = "indoor_terminal.plugins"


@dataclass(frozen=True)
class Plugin:
    name: str
    provides: tuple[str, ...]
    start: Callable[[Context], Mapping[str, Any]]
    requires: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()
    api_version: int = 1


class EventBus:
    def __init__(self, journal: EventStore):
        self.journal = journal
        self._listeners = {}
        self._lock = RLock()

    def subscribe(self, topic, listener):
        with self._lock:
            self._listeners.setdefault(topic, []).append(listener)
        def unsubscribe():
            with self._lock:
                self._listeners[topic].remove(listener)
        return unsubscribe

    def emit(self, topic, data):
        self.journal.add("event", topic, data=data)
        with self._lock:
            listeners = list(self._listeners.get(topic, ()))
        for listener in listeners:
            try:
                listener(dict(data))
            except Exception:
                self.journal.add("plugin", "Event listener failed", level="error", data={"topic": topic})


class Context:
    def __init__(self, settings, live, services, bus, scope):
        self.settings = settings
        self.live = live
        self._services = services
        self.events = bus
        self._scope = scope

    def require(self, name):
        return self._services[name]

    def on(self, topic, listener):
        self._scope.callback(self.events.subscribe(topic, listener))

    def on_stop(self, callback):
        self._scope.callback(callback)


class Host:
    def __init__(self, plugins, settings, live, journal):
        plugins = list(plugins)
        self._plugins = {p.name: p for p in plugins}
        if len(self._plugins) != len(plugins):
            raise ValueError("duplicate plugin identifier")
        self._settings = settings
        self._live = live
        self.events = EventBus(journal)
        self.services = {}
        self._stack = None

    def _order(self):
        owners = {}
        for p in self._plugins.values():
            if p.api_version != 1:
                raise ValueError(f"{p.name}: unsupported API version {p.api_version}")
            for cap in p.provides:
                if cap in owners:
                    raise ValueError(f"{cap}: multiple providers ({owners[cap]}, {p.name})")
                owners[cap] = p.name
        graph = {}
        for p in self._plugins.values():
            for cap in p.requires:
                if cap not in owners:
                    raise ValueError(f"{p.name}: missing {cap}")
            graph[p.name] = {owners[cap] for cap in p.requires + p.optional if cap in owners}
        try:
            return list(TopologicalSorter(graph).static_order())
        except CycleError as exc:
            raise ValueError(f"cyclic plugin dependencies: {exc.args[-1]}") from exc

    def start(self):
        if self._stack is not None:
            return
        services = {}
        with ExitStack() as lifetime:
            for name in self._order():
                p = self._plugins[name]
                deps = {k: services[k] for k in p.requires + p.optional if k in services}
                scope = lifetime.enter_context(ExitStack())
                ctx = Context(self._settings.get(name, {}), self._live, deps, self.events, scope)
                exports = p.start(ctx)
                if set(exports) != set(p.provides):
                    raise ValueError(f"{name}: services do not match plugin declaration")
                services.update(exports)
            self._stack = lifetime.pop_all()
            self.services = services

    def stop(self):
        stack, self._stack = self._stack, None
        self.services = {}
        if stack is not None:
            stack.close()


def discover(names):
    from .demo import demo
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        raise ValueError("plugins must be a list of installed plugin identifiers")
    if len(names) != len(set(names)):
        raise ValueError("duplicate plugin identifier")
    points = metadata.entry_points()
    group = points.select(group=GROUP) if hasattr(points, "select") else points.get(GROUP, ())
    plugins = []
    for name in names:
        matches = [ep for ep in group if ep.name == name]
        if name == "demo" and not matches:
            plugin = demo()
        elif len(matches) == 1 and name != "demo":
            plugin = matches[0].load()()
        else:
            raise ValueError(f"{name}: expected exactly one installed plugin")
        if not isinstance(plugin, Plugin) or plugin.name != name:
            raise ValueError(f"{name}: invalid plugin descriptor")
        plugins.append(plugin)
    return plugins
