# YASL — Yet Another Server Launcher for Minecraft

YASL 是一个基于 Python 的 Minecraft 服务端启动器，提供 **REST API**、**Web 监控面板**、**事件总线** 和 **可扩展插件系统**，支持 Forge / Paper / Purpur / Spigot 等主流服务端。

---

## 项目结构

```
pjyasl/
├── run.py                    # 启动入口，定义 JVM 参数并委托 LifeCycle
├── requirements.txt          # Python 依赖
├── server/                   # Minecraft 服务端文件（Forge / Paper）
├── yasl/                     # 核心模块
│   ├── __init__.py           # 包初始化
│   ├── main.py               # MinecraftServer — Java 进程生命周期管理
│   ├── life_cycle.py         # LifeCycle — 协同启动：扩展→API→Dashboard→服务器
│   ├── loader.py             # Load — 自动检测 Forge / Paper 类型
│   ├── api.py                # FastAPI REST API（/players, /command, /health）
│   ├── dashboard.py          # Gradio 监控面板（端口 8001）
│   ├── event_bus.py          # 事件总线 — 发布/订阅（20+ 事件类型）
│   ├── extension_loader.py   # 扩展加载器 — ExtensionBase / ExtensionManager
│   ├── commands.py           # CommandHelper — 100+ 原版 Minecraft 命令封装
│   ├── logging.py            # 日志解析、ANSI 颜色（16色/24位真彩）、级别过滤
│   ├── installer.py          # 依赖安装器 — 自动安装扩展 requirements.txt
│   └── config.json           # 全局配置文件
├── extensions/               # 扩展目录
│   ├── .installed.json       # 扩展安装状态（含版本/作者/repo 元信息）
│   ├── example/              # 示例扩展 — 监听玩家进出事件
│   ├── backup/               # 备份扩展 — 定时打包世界存档
│   └── playtime/             # 玩家时长统计扩展
```

---

## 核心功能一览

| 模块 | 功能 | 端口 |
|------|------|------|
| `MinecraftServer` | Java 进程启停、stdin/stdout 管道通信、Broken Pipe 检测与自动重启 | — |
| `LifeCycle` | 生命周期编排：扩展加载 → API → Dashboard → 游戏服务器 → 控制台 | — |
| `REST API` | `/players` 在线玩家、`/command` 发送命令、`/health` 健康检查 | `8000` |
| `Dashboard` | Gradio Web 面板：服务器状态、在线玩家、最近日志（自动刷新） | `8001` |
| `EventBus` | 发布/订阅事件总线，覆盖玩家进出、聊天、崩溃、掉刻等 20+ 事件 | — |
| `Extension` | 插件系统 — 自动扫描、加载、启用/禁用/卸载，支持声明作者/版本/Repo | — |
| `CommandHelper` | 面向对象的 100+ Minecraft 原版命令封装（异步） | — |
| `LogFilter` | 正则日志解析 + 级别过滤 + 16色/24位真彩 ANSI 终端着色 | — |

---

## 快速启动

### 1. 环境要求

- Python 3.10+
- Java 17+（Forge 1.19+）或 Java 21+（1.21+）
- Windows / Linux / macOS

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 放置服务端

将 Forge 或 Paper 服务端文件放入 `server/` 目录。启动器会自动检测类型：

- **Forge** → 检测 `server/libraries/net/minecraftforge/forge/` 目录
- **Paper / Purpur / Spigot** → 检测 `server/` 下的 `.jar` 文件名前缀

### 4. 配置（可选）

编辑 `yasl/config.json`：

```json
{
  "api": {
    "host": "0.0.0.0",
    "port": 8000,
    "api_key": "changeme",
    "require_api_key": true
  },
  "dashboard": {
    "enabled": true,
    "host": "0.0.0.0",
    "port": 8001,
    "share": false
  },
  "extensions": {
    "enabled": true,
    "auto_install_deps": true
  },
  "server": {
    "auto_start_broken_pipe_monitor": true,
    "log_level": "INFO",
    "use_colors": true
  }
}
```

JVM 参数可通过 `run.py` 直接定义（推荐），也可在 `config.json` 中覆盖：

```json
{
  "server": {
    "jvm_args": ["-Xms16G", "-Xmx16G", "-XX:+UseG1GC"]
  }
}
```

### 5. 启动

```bash
python run.py
```

启动后控制台支持交互命令：

| 命令 | 说明 |
|------|------|
| `stop` | 优雅关闭服务器 |
| `help` | 显示帮助 |
| 其他任意文本 | 直接作为命令发送至 Minecraft 服务端（如 `list`、`say hello`） |

---

## REST API

默认 `http://localhost:8000`，需要 API Key 认证。

### 在线玩家

```bash
curl -H "Authorization: Bearer changeme" http://localhost:8000/players
```

返回 `{ "count": 3, "players": ["Alice", "Bob", "Charlie"], "max_players": 20 }`

### 发送命令

```bash
curl -X POST http://localhost:8000/command \
  -H "Authorization: Bearer changeme" \
  -H "Content-Type: application/json" \
  -d '{"command": "list", "timeout": 5.0}'
```

### 健康检查（无需 Key）

```bash
curl http://localhost:8000/health
```

---

## 扩展（Extension）编写

扩展位于 `extensions/` 目录，每个扩展是一个子目录，其中包含 `main.py`。

### 最简示例

```python
# extensions/my_ext/main.py
from yasl.event_bus import EventType
from yasl.extension_loader import ExtensionBase
from yasl.logging import ExtensionLogger

_log = ExtensionLogger("my_ext")


class MyExtension(ExtensionBase):
    name = "my_ext"
    version = "1.0.0"
    author = "YourName"               # 可选
    repo = "https://github.com/..."   # 可选

    async def on_enable(self) -> None:
        self.subscribe(EventType.PLAYER_JOIN, self._on_join)
        self.subscribe(EventType.PLAYER_CHAT, self._on_chat)
        _log.info("已启用")

    async def on_disable(self) -> None:
        self.unsubscribe(EventType.PLAYER_JOIN, self._on_join)
        self.unsubscribe(EventType.PLAYER_CHAT, self._on_chat)
        _log.info("已禁用")

    def _on_join(self, player_name: str = "?", **kwargs) -> None:
        _log.info(f"{player_name} 加入了游戏")

    def _on_chat(self, player_name: str = "?", message: str = "", **kwargs) -> None:
        _log.info(f"{player_name} 说: {message}")
```

### 声明元信息

在扩展类的属性中声明 `version`、`author`、`repo`：

```python
class MyExtension(ExtensionBase):
    name = "my_ext"
    version = "2.0.0"
    author = "XieJi"
    repo = "https://github.com/xieji/pjyasl-my-ext"
```

这些信息会在扩展加载时由 `ExtensionManager` 读取并持久化到 `extensions/.installed.json`，可通过 `ExtensionManager.get_extension_meta(name)` 或 `list_extensions()` 查询。

### 使用 CommandHelper 发送命令

通过 `self.commands` 调用 Minecraft 原版命令：

```python
class MyExtension(ExtensionBase):
    async def on_enable(self):
        await self.commands.say("§a欢迎来到服务器！")
        await self.commands.give("PlayerName", "minecraft:diamond", 64)
        await self.commands.execute_as("@a", "say hello")
        await self.commands.list_players()      # 等效 /list
        await self.commands.save_all(flush=True) # 等效 /save-all flush
```

### 日志输出

扩展应使用 `ExtensionLogger` 替代 `print()`：

```python
from yasl.logging import ExtensionLogger

_log = ExtensionLogger("my_ext")

_log.info("普通信息")       # [INFO]  白色
_log.warn("警告消息")       # [WARN]  黄色
_log.error("错误消息")      # [ERROR] 红色
_log.debug("调试信息")      # [DEBUG] 青色
_log.done("操作完成")       # [DONE]  品红色
```

### 生命周期钩子

| 方法 | 触发时机 | 典型用途 |
|------|----------|----------|
| `on_load()` | 扩展模块被加载 | 初始化数据结构 |
| `on_enable()` | 扩展启用 | **注册事件监听** |
| `on_disable()` | 扩展禁用 | **注销事件监听**（避免泄漏） |
| `on_unload()` | 扩展卸载 | 清理资源 |

### 依赖安装

在扩展目录放置 `requirements.txt`，启动时自动安装（需 `extensions.auto_install_deps: true`）。

### 可用事件类型

```python
from yasl.event_bus import EventType

# 服务器生命周期
EventType.STARTING       # 服务器启动中
EventType.STARTED        # 启动完成（Done）
EventType.STOPPING       # 停止中
EventType.SHUTTING_DOWN  # 关闭中

# 玩家事件
EventType.PLAYER_JOIN    # 玩家加入
EventType.PLAYER_LEAVE   # 玩家离开
EventType.PLAYER_CHAT    # 聊天
EventType.PLAYER_COMMAND # 执行命令
EventType.PLAYER_SAY     # /say 广播
EventType.PLAYER_WHISPER # 私聊

# 性能 / 异常
EventType.CANT_KEEP_UP   # 服务器掉刻
EventType.CRASH          # 崩溃
EventType.ERROR          # 错误
EventType.FAIL           # 失败
EventType.SUCCESS        # 成功
```

---

## 配置参考

`yasl/config.json` 完整选项：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `api.host` | string | `0.0.0.0` | API 监听地址 |
| `api.port` | int | `8000` | API 端口（设为 0 禁用） |
| `api.api_key` | string | `changeme` | API 认证密钥 |
| `api.require_api_key` | bool | `true` | 是否要求 API Key |
| `dashboard.enabled` | bool | `true` | 是否启用监控面板 |
| `dashboard.host` | string | `0.0.0.0` | 面板监听地址 |
| `dashboard.port` | int | `8001` | 面板端口 |
| `dashboard.share` | bool | `false` | 是否创建 Gradio 公开链接 |
| `extensions.enabled` | bool | `true` | 是否加载扩展 |
| `extensions.auto_install_deps` | bool | `true` | 自动安装扩展依赖 |
| `server.jvm_args` | list | — | 自定义 JVM 参数（空时使用代码默认） |
| `server.log_level` | string | `INFO` | 日志级别 |
| `server.use_colors` | bool | `true` | 控制台 ANSI 彩色输出 |
| `server.filter_sources` | list | — | 过滤特定来源的日志 |

---

## 技术栈

- **语言**：Python 3.10+（全异步 asyncio）
- **Web 框架**：FastAPI（API）+ Gradio（Dashboard）
- **进程通信**：subprocess.Popen + stdin/stdout 管道 + asyncio.Queue 分发
- **日志着色**：16 色 ANSI / 24-bit 真彩色终端渲染
- **服务端支持**：Forge、Paper、Purpur、Spigot