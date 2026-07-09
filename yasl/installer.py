"""依赖安装器 — 支持 pip / uv，异步安装扩展依赖。"""
import asyncio
import subprocess
import sys
from pathlib import Path


async def _run_command(cmd: list[str]) -> bool:
    """异步运行安装命令。"""
    loop = asyncio.get_running_loop()
    try:
        proc = await loop.run_in_executor(
            None,
            lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=120),
        )
        return proc.returncode == 0
    except Exception:
        return False


def _has_tool(name: str) -> bool:
    import shutil

    return shutil.which(name) is not None


async def install_requirements(req_path: Path) -> bool:
    """安装 requirements.txt — 优先 uv，回退 pip。"""
    if not req_path.exists():
        return True

    # 尝试 uv
    if _has_tool("uv"):
        ok = await _run_command(["uv", "pip", "install", "-r", str(req_path)])
        if ok:
            return True

    # 回退 pip
    if _has_tool("pip") or _has_tool("pip3"):
        return await _run_command(
            [sys.executable, "-m", "pip", "install", "-r", str(req_path)]
        )

    return False