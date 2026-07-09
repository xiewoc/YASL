# YASL — Yet Another Server Launcher for Minecraft

YASL 是一个基于 Python 的 Minecraft 服务端启动器，提供 **REST API**、**Web 监控面板**、**事件总线** 和 **可扩展插件系统**，支持 Forge / Paper 等主流服务端。

---

## 项目结构

```
├── run.py                    # 启动入口（主流程、信号处理、JVM 参数）
├── requirements.txt          # Python 依赖
├── server/                   # Minecraft 服务端文件（Forge / Paper）
├── yasl/                     # 核心模块
│   ├── __init__.py           # 包导出，统一对外接口
│   ├── main.py               # MinecraftServer — Java 进程生命周期管理
│   ├── life_cycle.py         # LifeCycle — 协同启动：扩展→API→Dashboard→服务器
│   ├── loader.py             # Load — 自动检测 Forge / Paper
│   ├── api.py                # FastAPI REST API（/players, /command, /health）
│   ├── dashboard.py          # Gradio 监控面板（端口 8001）
│   ├── event_bus.py          # 事件总线 — 发布/订阅（玩家进出、服务器状态等）
│   ├── extension_loader.py   # 扩展加载器 — ExtensionBase / ExtensionManager
│   ├── commands.py           # CommandHelper — 全量 Minecraft 原版命令封装
│   ├── logging.py            # 日志解析、颜色方案（16色/24位真彩）、过滤
│   ├── installer.py          # 依赖安装器 — 自动安装扩展 requirements.txt
│   └── config.json           # 全局配置文件
├── extensions/               # 扩展目录
│   ├── example/              # 示例扩展 — 监听玩家进出事件
│   ├── backup/               # 备份扩展
│   └── playtime/             # 玩家时长统计扩展
```

## 核心功能一览

| 模块 | 功能 | 端口 |
|------|------|------|
| `MinecraftServer` | 管理 Java 进程启停、stdin/stdout、Broken Pipe 检测与自动重启 | — |
| `LifeCycle` | 按序启动：扩展加载 → API 服务 → Dashboard → 游戏服务器 | — |
| `REST API` | `/players` 在线玩家、`/command` 发送命令、`/health` 健康检查 | `8000` |
| `Dashboard` | Gradio 实时面板：服务器状态、在线玩家、最近日志 | `8001` |
| `EventBus` | 事件发布/订阅，支持 20+ 事件类型（玩家进出、聊天、崩溃等） | — |
| `Extension` | 插件式扩展系统，自动发现 `extensions/` 下的扩展并管理生命周期 | — |
| `CommandHelper` | 封装 100+ 原版命令为 Python 方法 | — |
| `LogFilter` | 日志级别过滤 + ANSI 16 色 / 24 位真彩着色 | — |

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

- **Forge**：检测 `server/libraries/net/minecraftforge/forge/` 目录
- **Paper / Purpur / Spigot**：检测 `server/` 下 `.jar` 文件名前缀

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

也可以在 `config.json` 中自定义 JVM 参数（优先级高于内置默认）：

```json
{
  "server": {
    "jvm_args": ["-Xms4G", "-Xmx8G", "-XX:+UseG1GC"]
  }
}
```

### 5. 启动

```bash
python run.py
```

启动后控制台提供交互命令：

| 命令 | 说明 |
|------|------|
| `stop` | 优雅关闭服务器 |
| `players` | 查看在线玩家 |
| `help` | 显示帮助 |
| 其他 | 直接发送至 Minecraft 服务端 |

---

## REST API 用法

默认运行在 `http://localhost:8000`，需要 API Key 认证。

### 查看在线玩家

```bash
curl -H "Authorization: Bearer changeme" http://localhost:8000/players
```

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

## 拓展编写

扩展位于 `extensions/` 目录，每个扩展是一个包含 `main.py` 的子目录。

### 最小示例

```python
# extensions/my_extension/main.py
from yasl.event_bus import EventType
from yasl.extension_loader import ExtensionBase


class MyExtension(ExtensionBase):
    name = "my_extension"
    version = "1.0.0"

    async def on_enable(self) -> None:
        # 注册事件监听
        self.subscribe(EventType.PLAYER_JOIN, self._on_join)
        self.subscribe(EventType.PLAYER_CHAT, self._on_chat)
        print("[MyExtension] 已启用")

    async def on_disable(self) -> None:
        # 务必注销监听，避免内存泄漏
        self.unsubscribe(EventType.PLAYER_JOIN, self._on_join)
        self.unsubscribe(EventType.PLAYER_CHAT, self._on_chat)
        print("[MyExtension] 已禁用")

    def _on_join(self, player_name: str = "?", **kwargs) -> None:
        print(f"[MyExtension] {player_name} 加入了游戏")

    def _on_chat(self, player_name: str = "?", message: str = "", **kwargs) -> None:
        print(f"[MyExtension] {player_name} 说: {message}")
```

### 使用 CommandHelper 发送命令

扩展可通过 `self.commands` 调用 Minecraft 原版命令：

```python
class MyExtension(ExtensionBase):
    async def on_enable(self):
        # 群发消息
        await self.commands.say("欢迎来到服务器！")
        # 给玩家物品
        await self.commands.give("PlayerName", "minecraft:diamond", 64)
        # 执行 execute 子命令
        await self.commands.execute_as("@a", "say hello")
```

### 扩展生命周期钩子

| 方法 | 触发时机 |
|------|----------|
| `on_load()` | 扩展模块被加载时 |
| `on_enable()` | 扩展启用时（**在此注册事件**） |
| `on_disable()` | 扩展禁用时（**在此注销事件**） |
| `on_unload()` | 扩展卸载时 |

### 依赖安装

如果扩展需要额外的 Python 包，在其目录下放置 `requirements.txt`，启动时会自动安装（需确保 `config.json` 中 `extensions.auto_install_deps` 为 `true`）。

### 可用事件类型

```python
from yasl.event_bus import EventType

# 服务器生命周期
EventType.STARTING       # 服务器启动中
EventType.STARTED        # 服务器启动完成
EventType.STOPPING       # 服务器停止中
EventType.SHUTTING_DOWN  # 服务器关闭

# 玩家事件
EventType.PLAYER_JOIN    # 玩家加入
EventType.PLAYER_LEAVE   # 玩家离开
EventType.PLAYER_CHAT    # 玩家聊天
EventType.PLAYER_COMMAND # 玩家执行命令
EventType.PLAYER_SAY     # 服务端说话 (/say)
EventType.PLAYER_WHISPER # 私聊

# 性能/异常
EventType.CANT_KEEP_UP   # 服务器掉刻
EventType.CRASH          # 崩溃
EventType.ERROR          # 错误
EventType.FAIL           # 失败
EventType.SUCCESS        # 成功
```

---

## 配置说明

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
| `server.jvm_args` | list | — | 自定义 JVM 参数 |
| `server.log_level` | string | `INFO` | 日志级别 |
| `server.use_colors` | bool | `true` | 控制台彩色输出 |

---

## 技术栈

- **语言**：Python 3.10+
- **Web 框架**：FastAPI（API）+ Gradio（Dashboard）
- **异步**：asyncio
- **进程管理**：subprocess + stdin/stdout 管道通信
- **服务端支持**：Forge、Paper、Purpur、Spigot
