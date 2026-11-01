# Foyer Hub · 住户控制中枢

一个本地优先的住户 C/S 框架。后端管理设备与会话，前端通过统一 API 查询状态和发出操作。核心包包含 PC 网页、插件宿主、脱敏事件日志、操作闸门和纯内存演练插件。新站点通过安装适配器扩展能力。

## 本地运行

Python 3.9+，从仓库根目录执行：

```powershell
python -m pip install -e .
python -m indoor_terminal --config config.example.json
```

打开 [PC 网页](http://127.0.0.1:8080/)。默认是 DRY-RUN，注册、发现及同步返回模拟结果。呼梯默认关闭。`demo` 拒绝 LIVE；实际适配器需按站点单独安装和配置。运行 `python -m unittest discover -s tests -v` 验证演练、依赖和接口。

## 插件中心

首版开发目标是让授权管理员在 PC 网页发现、安装、升级、回退和卸载后端插件，宿主与无关会话保持运行。通话中的插件等待挂断再切换，网页分别显示已安装版本和实际运行版本。公开索引只收录公开插件，私有适配器通过授权来源或本地 wheel 分发。

**当前原型只加载已在本机安装并显式选择的插件。** 在线管理和不停机热更新已纳入正式规则，仍待实现与验收。详见[插件中心规范](docs/plugin-center.md)。

## 目录

| 路径 | 内容 |
| --- | --- |
| `src/indoor_terminal/plugins.py` | entry points 发现、依赖预检、作用域和生命周期 |
| `src/indoor_terminal/service.py` | 通用住户操作、权限开关、冷却、能力状态 |
| `src/indoor_terminal/events.py`、`demo.py` | 脱敏日志、内存演练插件 |
| `src/indoor_terminal/web.py`、`static/` | localhost HTTP API 和 PC 网页 |
| `docs/`、`tests/` | 插件开发约束、路线、产品视觉设计、离线测试 |

每户只有一个真实站点后端。正式后端的设备插物业网线，另一网络面服务家庭客户端和家庭设备。开发优先做 PC 网页，后续验证有线 Android 平板常驻服务，再迁移独立 ARM / x86 主机。Flutter 的 Android、iOS 和 x86 桌面客户端、WebSocket 推送和 WebRTC 媒体是后续目标。当前只提供本地 HTTP 接口。

开发者见[插件契约](docs/plugins.md)、[路线与边界](docs/roadmap.md)、[住户界面](docs/ui-design.md)和[协作规则](AGENTS.md)。本仓库的代码和文档采用 [MIT 许可证](LICENSE)。独立分发的插件由各自的权利人决定授权方式。
