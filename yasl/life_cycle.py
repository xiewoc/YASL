"""统一生命周期 — 本体 + 扩展 + API + Dashboard 协同启停。"""
import asyncio
import threading
from collections.abc import AsyncGenerator
from datetime import datetime
from pathlib import Path
from typing import Optional

from yasl.main import MinecraftServer, ManagedServer
from yasl.extension_loader import ExtensionManager
from yasl.commands import CommandHelper
from yasl.api import set_server, run_api, load_config
from yasl.dashboard import run_dashboard


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


class LifeCycle:
    """管理服务器 + 扩展 + API + Dashboard 的完整生命周期。"""

    def __init__(
        self,
        server: Optional[MinecraftServer] = None,
        extensions_dir: Optional[Path] = None,
    ):
        self._server = server or MinecraftServer()
        self._commands = CommandHelper()
        self._ext_manager = ExtensionManager(extensions_dir, commands=self._commands)
        self._api_thread: Optional[threading.Thread] = None
        self._dashboard_thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # 启动
    # ------------------------------------------------------------------
    async def startup(self, jvm_args: list[str] | None = None) -> AsyncGenerator[MinecraftServer, None]:
        """按顺序启动: 扩展 → API → Dashboard → 服务器。"""
        if jvm_args is None:
            jvm_args = []

        config = load_config()
        api_cfg = config.get("api", {})
        dash_cfg = config.get("dashboard", {})

        # 1. 加载 & 启用扩展
        print(f"[{_ts()}] [LifeCycle] 正在加载扩展...")
        await self._ext_manager.load_all()
        await self._ext_manager.enable_all()

        # 2. 启动 API（注入 server）
        set_server(self._server)
        if api_cfg.get("port", 8000) > 0:
            self._api_thread = threading.Thread(
                target=run_api,
                args=(api_cfg.get("host", "0.0.0.0"), api_cfg.get("port", 8000)),
                daemon=True,
            )
            self._api_thread.start()
            print(
                f"  API 服务 → "
                f"http://{api_cfg.get('host', '0.0.0.0')}:{api_cfg.get('port', 8000)}"
            )

        # 3. 启动 Dashboard
        if dash_cfg.get("enabled", True):
            self._dashboard_thread = threading.Thread(
                target=run_dashboard,
                args=(
                    dash_cfg.get("host", "0.0.0.0"),
                    dash_cfg.get("port", 8001),
                    dash_cfg.get("share", False),
                ),
                daemon=True,
            )
            self._dashboard_thread.start()
            print(
                f"  监控面板 → "
                f"http://{dash_cfg.get('host', '0.0.0.0')}:{dash_cfg.get('port', 8001)}"
            )

        # 4. 绑定 CommandHelper 到 server
        self._commands.bind(self._server)

        # 5. 启动服务器（含 Broken Pipe 监控）
        async with ManagedServer(self._server) as srv:
            await srv.start(extra_args=jvm_args)
            print(f"  PID: {srv.process.pid if srv.process else 'N/A'}")
            yield srv

    # ------------------------------------------------------------------
    # 关闭
    # ------------------------------------------------------------------
    async def shutdown(self) -> None:
        print(f"[{_ts()}] [LifeCycle] 正在禁用扩展...")
        await self._ext_manager.disable_all()
        await self._ext_manager.unload_all()
        print(f"[{_ts()}] [LifeCycle] 关闭完成")

    @property
    def extension_manager(self) -> ExtensionManager:
        return self._ext_manager