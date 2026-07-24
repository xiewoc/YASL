"""统一生命周期 — 本体 + 扩展 + API + Dashboard 协同启停。"""
import asyncio
import signal
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from yasl.logging import ExtensionLogger
from yasl.main import MinecraftServer
from yasl.extension_loader import ExtensionManager
from yasl.commands import CommandHelper
from yasl.api import set_server, run_api, load_config
from yasl.dashboard import run_dashboard

_log = ExtensionLogger("LifeCycle")


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


class LifeCycle:
    """管理服务器 + 扩展 + API + Dashboard 的完整生命周期。

    用法:
        await LifeCycle().run()
    """

    def __init__(
        self,
        server: Optional[MinecraftServer] = None,
        extensions_dir: Optional[Path] = None,
    ):
        # 延迟创建：run() 中读取 config 后再实例化 MinecraftServer
        self._server = server
        self._commands = CommandHelper()
        self._ext_manager = ExtensionManager(extensions_dir, commands=self._commands)
        self._api_thread: Optional[threading.Thread] = None
        self._dashboard_thread: Optional[threading.Thread] = None

        self._shutdown_event: asyncio.Event = asyncio.Event()

    # ------------------------------------------------------------------
    # 运行（完整生命周期）
    # ------------------------------------------------------------------
    async def run(self, jvm_args: Optional[List[str]] = None, filter_sources: Optional[list[str]] = None) -> None:
        """完全自主运行：信号 → 启动全部 → 控制台 → 优雅关闭。"""
        self._setup_signals()

        config = load_config()
        api_cfg = config.get("api", {})
        dash_cfg = config.get("dashboard", {})
        server_cfg = config.get("server", {})

        if self._server is None:
            # 从 config 读取 filter_sources，run() 参数可覆盖
            cfg_filter: Optional[list[str]] = server_cfg.get("filter_sources")
            if filter_sources is None and cfg_filter is not None:
                filter_sources = list(cfg_filter)

            self._server = MinecraftServer(
                log_level=server_cfg.get("log_level", "INFO"),
                use_colors=server_cfg.get("use_colors", True),
                filter_sources=filter_sources,
            )

        if jvm_args is None:
            jvm_args = self._resolve_jvm_args(config)

        print("=" * 50)
        print("  YASL - Minecraft 服务器启动器")
        print("=" * 50)

        try:
            # ── Phase 1: 扩展 ──
            _log.info("正在加载扩展...")
            await self._ext_manager.load_all()
            await self._ext_manager.enable_all()

            # ── Phase 2: API ──
            set_server(self._server)
            if api_cfg.get("port", 8000) > 0:
                self._api_thread = threading.Thread(
                    target=run_api,
                    args=(api_cfg.get("host", "0.0.0.0"), api_cfg.get("port", 8000)),
                    daemon=True,
                )
                self._api_thread.start()
                _log.info(
                    f"API → "
                    f"http://{api_cfg.get('host', '0.0.0.0')}:{api_cfg.get('port', 8000)}"
                )

            # ── Phase 3: Dashboard ──
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
                _log.info(
                    f"Dashboard → "
                    f"http://{dash_cfg.get('host', '0.0.0.0')}:{dash_cfg.get('port', 8001)}"
                )

            # ── Phase 4: 绑定命令 ──
            self._commands.bind(self._server)

            # ── Phase 5: 服务器 ──
            auto_monitor = server_cfg.get("auto_start_broken_pipe_monitor", True)
            await self._server.start(extra_args=jvm_args)
            _log.info(f"服务器已启动, PID: {self._server.process.pid if self._server.process else 'N/A'}")

            if auto_monitor:
                await self._server.start_broken_pipe_monitor()

            print("  输入 'help' 查看命令，'stop' 关闭服务器")
            print("-" * 50)

            # ── Phase 6: 控制台 & 等待 ──
            console_task = asyncio.create_task(self._console_loop())
            signal_task = asyncio.create_task(self._shutdown_event.wait())

            done, pending = await asyncio.wait(
                [console_task, signal_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass
        except Exception:
            _log.error(f"启动失败")
            raise
        finally:
            await self.shutdown()

    # ------------------------------------------------------------------
    # 关闭（逆序：服务器 → API / Dashboard → 扩展）
    # ------------------------------------------------------------------
    async def shutdown(self) -> None:
        _log.info("正在关闭...")

        # 1) 停止服务器
        if self._server is not None:
            await self._server.stop()

        # 2) API / Dashboard 线程会随主进程退出（daemon）
        #    若需主动等待可在此 join, 但 daemon 线程无需显式等待

        # 3) 禁用 & 卸载扩展
        _log.info("正在禁用扩展...")
        await self._ext_manager.disable_all()
        await self._ext_manager.unload_all()

        _log.info("关闭完成")

    # ------------------------------------------------------------------
    # 控制台交互
    # ------------------------------------------------------------------
    async def _console_loop(self) -> None:
        """控制台命令输入循环。"""
        assert self._server is not None
        srv = self._server
        loop = asyncio.get_running_loop()
        while srv.running:
            try:
                line = await loop.run_in_executor(None, input)
            except (EOFError, KeyboardInterrupt):
                break

            line = line.strip()
            if not line:
                continue

            if line == "stop":
                print(f"[{_ts()}] 正在关闭服务器...")
                break

            if line == "help":
                print("  stop    - 关闭服务器")
                print("  players - 查看在线玩家 (API)")
                print("  help    - 显示帮助")
                continue

            result = await srv.send_command_async(line)
            if result.get("lines"):
                for l in result["lines"]:
                    print(l)
            elif result.get("timed_out"):
                print("(命令超时)")

        if not self._shutdown_event.is_set():
            self._shutdown_event.set()

    # ------------------------------------------------------------------
    # 信号处理
    # ------------------------------------------------------------------
    def _setup_signals(self) -> None:
        """注册 SIGINT / SIGTERM 信号处理器。"""
        loop = asyncio.get_running_loop()

        def _handler(*args):
            if not self._shutdown_event.is_set():
                print(f"\n[{_ts()}] 收到退出信号，正在优雅关闭...")
                self._shutdown_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _handler, sig)
            except (NotImplementedError, ValueError):
                signal.signal(sig, lambda s, f: _handler())

    # ------------------------------------------------------------------
    # JVM 参数
    # ------------------------------------------------------------------
    @staticmethod
    def _resolve_jvm_args(config: dict) -> List[str]:
        """从 config 读取 JVM 参数，没有则用内置默认。"""
        cfg_args: List[str] = config.get("server", {}).get("jvm_args", [])
        if cfg_args:
            _log.info(f"使用 config.json 中的 {len(cfg_args)} 个 JVM 参数")
            return cfg_args

        defaults = [
            "-Xms16G", "-Xmx16G",
            "-Xss1M",
            "-XX:+UseG1GC",
            "-server",
            "-XX:+ParallelRefProcEnabled",
            "-XX:MaxGCPauseMillis=200",
            "-XX:+AlwaysPreTouch",
            "-XX:+DisableExplicitGC",
            "-XX:InitiatingHeapOccupancyPercent=40",
            "-XX:SurvivorRatio=8",
            "-XX:+PerfDisableSharedMem",
            "-XX:MaxTenuringThreshold=15",
            "-XX:+UnlockExperimentalVMOptions",
            "-XX:G1MixedGCLiveThresholdPercent=90",
            "-XX:G1RSetUpdatingPauseTimePercent=5",
            "-XX:MetaspaceSize=1G",
            "-XX:MaxMetaspaceSize=2G",
            "-XX:+UseStringDeduplication",
            "-Djava.awt.headless=true",
        ]
        _log.info(f"使用 {len(defaults)} 个内置默认 JVM 参数")
        return defaults

    @property
    def extension_manager(self) -> ExtensionManager:
        return self._ext_manager