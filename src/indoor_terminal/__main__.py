import argparse
import json
import signal
import threading
from pathlib import Path

from .service import IndoorTerminalService
from .web import DashboardServer


def main(argv=None):
    parser = argparse.ArgumentParser(description="Indoor Terminal PC dashboard")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--port", type=int)
    args = parser.parse_args(argv)
    cfg = json.loads(args.config.read_text(encoding="utf-8-sig")) if args.config else {}
    web = cfg.get("web", {})
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    service = IndoorTerminalService(cfg, live=args.live)
    dashboard = None
    try:
        service.start()
        dashboard = DashboardServer(service, "127.0.0.1", args.port if args.port is not None else web.get("port", 8080),
                                    web.get("api_token", ""))
        dashboard.start()
        print(f"Indoor Terminal: http://127.0.0.1:{dashboard.address[1]}/", flush=True)
        stop.wait()
    finally:
        if dashboard:
            dashboard.stop()
        service.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
