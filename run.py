"""YASL 启动入口 — 使用 LifeCycle 统一管理生命周期。"""
import asyncio
import signal
import sys
import os
from datetime import datetime
from typing import List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from yasl.life_cycle import LifeCycle
from yasl.main import MinecraftServer
from yasl.api import load_config


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


# ---------------------------------------------------------------------------
# 信号处理
# ---------------------------------------------------------------------------
_shutdown_event: asyncio.Event | None = None


def _signal_handler(signum, frame):
    if _shutdown_event:
        print(f"\n[{_ts()}] 收到退出信号，正在优雅关闭...")
        _shutdown_event.set()


def _setup_signals():
    signal.signal(signal.SIGINT, _signal_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _signal_handler)


# ---------------------------------------------------------------------------
# JVM 参数构建
# ---------------------------------------------------------------------------
def _build_jvm_args() -> List[str]:
    """
    构建 JVM 启动参数列表，优先级：config.json > 内置默认。

    在 config.json 中配置：
        "server": { "jvm_args": ["-Xms4G", "-Xmx8G", "-XX:+UseG1GC"] }
    """
    config = load_config()
    cfg_args: List[str] = config.get("server", {}).get("jvm_args", [])

    if cfg_args:
        print(f"  [JVM] 使用 config.json 中的 {len(cfg_args)} 个参数")
        return cfg_args

    defaults = [
        "-Xms4G",
        "-Xmx8G",
        "-XX:+UseG1GC",
        "-XX:+UnlockExperimentalVMOptions",
        "-XX:G1NewSizePercent=30",
        "-XX:G1MaxNewSizePercent=60",
        "-XX:InitiatingHeapOccupancyPercent=40",
        "-XX:+ParallelRefProcEnabled",
        "-XX:MaxGCPauseMillis=150",
        "-XX:+AlwaysPreTouch",
        "-XX:+UseStringDeduplication",
        "-Djava.awt.headless=true",
    ]
    print(f"  [JVM] 使用 {len(defaults)} 个内置默认参数")
    return defaults


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
async def _handle_console(server: MinecraftServer):
    """控制台命令输入循环。"""
    loop = asyncio.get_running_loop()
    while server.running:
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

        result = await server.send_command_async(line)
        if result["lines"]:
            for l in result["lines"]:
                print(l)
        elif result["timed_out"]:
            print("(命令超时)")


async def main():
    global _shutdown_event

    _setup_signals()
    _shutdown_event = asyncio.Event()

    jvm_args = _build_jvm_args()

    print("=" * 50)
    print("  YASL - Minecraft 服务器启动器")
    print("=" * 50)

    life = LifeCycle()

    try:
        async for srv in life.startup(jvm_args=jvm_args):
            print(f"  输入 'help' 查看命令，'stop' 关闭服务器")
            print("-" * 50)

            console_task = asyncio.create_task(_handle_console(srv))
            shutdown_task = asyncio.create_task(_shutdown_event.wait())

            done, pending = await asyncio.wait(
                [console_task, shutdown_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            for t in pending:
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass
    finally:
        await life.shutdown()
        print(f"[{_ts()}] 服务器已关闭")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n[{_ts()}] 程序被中断")