# 插件开发

本文描述**当前已实现的 SDK**。宿主通过 `indoor_terminal.plugins` entry point 查找本机已安装且在配置中明确列出的可信 Python 包。公开宿主与适配器的依赖方向为 **适配器 → 宿主 API**。正式首版的仓库、在线安装与卸载、版本热切换及私有分发遵循[插件中心规范](plugin-center.md)。

## 最小例子

```toml
[project.entry-points."indoor_terminal.plugins"]
"local.example" = "example_provider:factory"
```

```python
from indoor_terminal.plugins import Plugin

def factory():
    def start(ctx):
        if ctx.live:
            raise ValueError("example is offline only")
        def register():
            result = {"ok": True, "dry_run": True}
            ctx.events.emit("station.registration.result", result)
            return result
        return {"station.register@1": register}
    return Plugin("local.example", ("station.register@1",), start)
```

在宿主配置中设置 `"plugins": ["local.example"]`，即可复用现有网页的注册按钮。只安装公开包时用内置的 `demo`。更换小区时安装新的包，选择新的提供者；UI 和住户功能只消费能力。特定站点的配置放在 `settings[插件 ID]` 或本地受限文件中。

## 契约与生命周期

- `Plugin(name, provides, start, requires=(), optional=(), api_version=1)` 是公开契约。工厂只构造描述符。能力键以主版本结尾。当前网页识别 `station.register@1`、`station.discover@1`、`content.sync@1` 和 `elevator.call@1`，操作返回可序列化的结果。
- 同一能力只能有一个启用的提供者。宿主在启动资源之前检查重名、缺必需依赖、版本及依赖环；可选能力缺失时可不启用相应功能。消费者通过 `ctx.require(key)` 获取已声明且可用的服务。
- `start(ctx)` 返回能力到服务对象的映射。获取 SDK 句柄、订阅、任务等资源后立即使用 `ctx.on_stop(cleanup)`。启动失败按逆序回收已申请资源，停止时先释放消费者再释放提供者。当前原型需重启宿主才能应用插件选择变化；首版交付要求支持按插件热切换。
- `ctx.on(topic, callback)` 注册的监听随作用域撤销；`ctx.events.emit(topic, data)` 投递业务事实并记录日志。当前监听同步调用，耗时 I/O 或媒体数据应转给插件自有队列。事件负载仅传通用业务字段。事件日志会脱敏，但不能用它净化任意原始报文。
- `ctx.live` 由宿主显式决定，适配器在演练模式下禁止实际设备 I/O。公开 HTTP 接口的呼梯开关、确认和冷却必须通过后才会调用插件。插件是可信本地代码，不是进程隔离的沙箱。

设计借鉴 [Cordis 的服务注入](https://github.com/cordiverse/cordis/blob/main/packages/core/src/registry.ts)和作用域管理。当前使用标准库的 [entry points](https://packaging.python.org/en/latest/guides/creating-and-discovering-plugins/)、拓扑排序及 ExitStack。需要动态绑定时可评估 [Pelix/iPOPO](https://ipopo.readthedocs.io/en/latest/)；多个实现响应同一钩子的场景可参考 [pluggy](https://pluggy.readthedocs.io/en/stable/)。
