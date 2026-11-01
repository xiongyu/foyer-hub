from .plugins import Plugin


def demo():
    def start(ctx):
        if ctx.live:
            raise ValueError("demo runs only in dry-run mode")
        def simulate():
            return {"ok": True, "dry_run": True}
        return {cap: simulate for cap in capabilities}
    capabilities = ("station.register@1", "station.discover@1", "content.sync@1", "elevator.call@1")
    return Plugin("demo", capabilities, start)
