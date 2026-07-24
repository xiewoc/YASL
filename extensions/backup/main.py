"""自动备份扩展 — 定时打包指定目录，备份前可执行 save-all flush。

从同目录下的 config.json 读取配置。
"""
import asyncio
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from yasl.extension_loader import ExtensionBase
from yasl.logging import ExtensionLogger

_log = ExtensionLogger("backup")

# 项目根目录（run.py / extensions / server 的父级）
ROOT = Path(__file__).parent.parent.parent


def _load_config(config_path: Path) -> dict[str, Any]:
    """加载 config.json，缺失则返回默认值。"""
    defaults: dict[str, Any] = {
        "backup_dir": "backups",
        "interval_minutes": 30,
        "max_backup_size_mb": 0,
        "keep_count": 10,
        "source_dirs": ["server/world"],
        "save_all_before_backup": True,
    }
    if config_path.is_file():
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
            defaults.update(raw)
        except (json.JSONDecodeError, TypeError):
            pass
    return defaults


class BackupExtension(ExtensionBase):
    name = "backup"
    version = "1.0.0"

    _task: asyncio.Task | None = None
    _source_dirs: list[Path] = []
    _dest_dir: Path | None = None

    # 从配置读取的运行时值
    _interval_seconds: float = 1800.0
    _max_size_bytes: int = 0
    _keep_count: int = 10
    _save_all_before_backup: bool = True

    async def on_enable(self) -> None:
        config_path = Path(__file__).with_name("config.json")
        cfg = _load_config(config_path)

        # 解析备份目标目录
        backup_dir_raw = cfg.get("backup_dir", "backups")
        backup_dir_path = Path(backup_dir_raw)
        if backup_dir_path.is_absolute():
            self._dest_dir = backup_dir_path
        else:
            self._dest_dir = Path(__file__).parent / backup_dir_path

        # 间隔（分钟）
        interval_min = max(1, int(cfg.get("interval_minutes", 30)))
        self._interval_seconds = interval_min * 60.0

        # 备份区大小上限（MB），0 表示不限制
        max_mb = max(0, int(cfg.get("max_backup_size_mb", 0)))
        self._max_size_bytes = max_mb * 1024 * 1024

        # 保留数量（与大小限制可同时生效）
        self._keep_count = max(1, int(cfg.get("keep_count", 10)))

        # 备份前是否执行 save-all flush
        self._save_all_before_backup = bool(cfg.get("save_all_before_backup", True))

        # 解析源目录列表
        raw_dirs: Sequence[str] = cfg.get("source_dirs", ["server/world"])
        self._source_dirs = []
        for d in raw_dirs:
            p = Path(d)
            if not p.is_absolute():
                p = ROOT / p
            if p.is_dir():
                self._source_dirs.append(p)
            else:
                _log.warn(f"源目录不存在，已跳过: {p}")

        if not self._source_dirs:
            _log.error("没有可用的源目录，扩展不会执行备份")
            self._dest_dir.mkdir(parents=True, exist_ok=True)
            return

        self._dest_dir.mkdir(parents=True, exist_ok=True)

        sources_str = ", ".join(p.name for p in self._source_dirs)
        self._task = asyncio.create_task(self._backup_loop())
        _log.info(
            f"已启用 — 间隔 {interval_min} 分钟, "
            f"备份 {sources_str} → {self._dest_dir}, "
            f"保留 {self._keep_count} 份"
            + (f", 上限 {max_mb} MB" if self._max_size_bytes > 0 else "")
            + (", 备份前 save-all" if self._save_all_before_backup else "")
        )

    async def on_disable(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        _log.info("已禁用")

    async def _backup_loop(self) -> None:
        """主备份循环 — 先立即执行一次，然后按间隔重复。"""
        await asyncio.sleep(5)

        while True:
            try:
                await self._do_backup()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                _log.error(f"备份失败: {e}")

            await asyncio.sleep(self._interval_seconds)

    async def _do_backup(self) -> None:
        if not self._dest_dir or not self._source_dirs:
            return

        # 备份前强制执行世界数据落盘
        if self._save_all_before_backup:
            try:
                await self.commands.raw("save-all flush", timeout=10.0)
                _log.info("已执行 save-all flush (数据落盘)")
            except Exception as e:
                _log.warn(f"save-all flush 失败: {e}")

        loop = asyncio.get_running_loop()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        for src in self._source_dirs:
            if not src.is_dir():
                _log.warn(f"源目录不存在，跳过: {src}")
                continue

            base_name = src.name
            zip_path = self._dest_dir / f"{base_name}_backup_{ts}"

            def _compress(src_dir: Path = src, dst_path: Path = zip_path) -> str:
                return shutil.make_archive(
                    str(dst_path), "zip",
                    root_dir=src_dir.parent,
                    base_dir=src_dir.name,
                )

            try:
                result_path = await loop.run_in_executor(None, _compress)
                _log.done(f"✓ {Path(result_path).name}")
            except Exception as e:
                _log.error(f"压缩 {src} 失败: {e}")

        # 按保留数量和大小上限清理
        await loop.run_in_executor(None, self._cleanup)

    def _cleanup(self) -> None:
        if not self._dest_dir:
            return

        zips = sorted(
            self._dest_dir.glob("*_backup_*.zip"),
            key=lambda p: p.stat().st_mtime,
        )

        # 1) 按数量限制清理
        while len(zips) > self._keep_count:
            oldest = zips.pop(0)
            oldest.unlink(missing_ok=True)

        # 2) 按大小上限清理（从最旧的开始删除）
        if self._max_size_bytes > 0 and zips:
            total = sum(p.stat().st_size for p in zips)
            while total > self._max_size_bytes and zips:
                oldest = zips.pop(0)
                total -= oldest.stat().st_size
                oldest.unlink(missing_ok=True)