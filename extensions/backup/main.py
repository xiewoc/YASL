"""自动备份扩展 — 定时打包 server/world/ 目录。"""
import asyncio
import shutil
from datetime import datetime
from pathlib import Path

from yasl.event_bus import EventType
from yasl.extension_loader import ExtensionBase


class BackupExtension(ExtensionBase):
    name = "backup"
    version = "1.0.0"

    INTERVAL_MINUTES = 30  # 备份间隔（分钟）

    _task: asyncio.Task | None = None
    _source: Path | None = None
    _dest_dir: Path | None = None

    async def on_enable(self) -> None:
        self._source = Path(__file__).parent.parent.parent / "server" / "world"
        self._dest_dir = Path(__file__).parent / "backups"
        self._dest_dir.mkdir(parents=True, exist_ok=True)

        self._task = asyncio.create_task(self._backup_loop())
        print(f"  [Backup] 已启用，每 {self.INTERVAL_MINUTES} 分钟备份一次")

    async def on_disable(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        print("  [Backup] 已禁用")

    async def _backup_loop(self) -> None:
        """主备份循环 — 先立即执行一次，然后按间隔重复。"""
        # 首次延迟 5 秒，等待服务器启动
        await asyncio.sleep(5)

        while True:
            try:
                await self._do_backup()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"  [Backup] 备份失败: {e}")

            await asyncio.sleep(self.INTERVAL_MINUTES * 60)

    async def _do_backup(self) -> None:
        src = self._source
        dst = self._dest_dir
        if not src or not src.is_dir() or not dst:
            print("  [Backup] 源目录不存在，跳过")
            return

        loop = asyncio.get_running_loop()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_path = dst / f"world_backup_{ts}"

        def _compress() -> str:
            return shutil.make_archive(
                str(zip_path), "zip", root_dir=src.parent, base_dir="world"
            )

        result_path = await loop.run_in_executor(None, _compress)
        print(f"  [Backup] ✓ {Path(result_path).name}")

        # 清理旧备份，只保留最近 10 个
        await loop.run_in_executor(None, self._cleanup_old)

    def _cleanup_old(self, keep: int = 10) -> None:
        if not self._dest_dir:
            return
        zips = sorted(self._dest_dir.glob("world_backup_*.zip"))
        for old in zips[:-keep]:
            old.unlink()