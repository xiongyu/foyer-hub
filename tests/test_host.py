import json
import unittest
import urllib.request

from indoor_terminal.events import EventStore
from indoor_terminal.plugins import Host, Plugin, discover
from indoor_terminal.service import IndoorTerminalService, OperationRejected
from indoor_terminal.web import DashboardServer


class PluginTests(unittest.TestCase):
    def test_dependencies_scoped_events_and_reverse_cleanup(self):
        seen = []
        def provide(ctx):
            ctx.on_stop(lambda: seen.append("provider stopped"))
            return {"fixture@1": lambda: 42}
        def consume(ctx):
            self.assertEqual(ctx.require("fixture@1")(), 42)
            ctx.on("ready", lambda data: seen.append(data["value"]))
            ctx.on_stop(lambda: seen.append("consumer stopped"))
            return {}
        host = Host([Plugin("consumer", (), consume, requires=("fixture@1",)),
                     Plugin("provider", ("fixture@1",), provide)], {}, False, EventStore())
        host.start()
        host.events.emit("ready", {"value": "received"})
        host.stop()
        host.events.emit("ready", {"value": "unexpected"})
        self.assertEqual(seen, ["received", "consumer stopped", "provider stopped"])

    def test_preflight_before_effects_and_partial_failure_rollback(self):
        effects = []
        def start(ctx):
            effects.append("resource")
            ctx.on_stop(lambda: effects.append("released"))
            raise RuntimeError("failed")
        p = Plugin("one", ("a@1",), start)
        for bad in [Plugin("missing", (), start, ("b@1",)),
                    Plugin("conflict", ("a@1",), start),
                    Plugin("cycle", ("cycle@1",), start, ("cycle@1",))]:
            with self.assertRaises(ValueError):
                Host([p,bad], {}, False, EventStore()).start()
        self.assertEqual(effects, [])
        with self.assertRaises(RuntimeError):
            Host([p], {}, False, EventStore()).start()
        self.assertEqual(effects, ["resource", "released"])

    def test_unknown_plugin_is_not_replaced_by_demo(self):
        with self.assertRaises(ValueError):
            discover(["uninstalled.example"])

    def test_dashboard_and_control_gates(self):
        svc = IndoorTerminalService({"elevator":{"enabled":True}})
        svc.start()
        self.addCleanup(svc.stop)
        web = DashboardServer(svc, "127.0.0.1", 0)
        web.start()
        self.addCleanup(web.stop)
        client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        base = "http://127.0.0.1:" + str(web.address[1])
        with client.open(base) as r:
            self.assertIn(b'id="register"', r.read())
        with client.open(base + "/api/register", data=b"{}") as r:
            self.assertEqual(json.load(r)["result"], {"ok":True, "dry_run":True})
        with self.assertRaises(OperationRejected):
            svc.call_elevator("incorrect")
        self.assertTrue(svc.call_elevator("CALL_ELEVATOR")["dry_run"])
        with self.assertRaises(OperationRejected):
            svc.call_elevator("CALL_ELEVATOR")
        with self.assertRaises(ValueError):
            IndoorTerminalService({}, live=True).start()
