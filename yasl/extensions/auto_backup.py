"""
自动备份扩展

功能:
- 每2小时自动备份 Minecraft 世界
- 每10秒检查一次是否需要备份
- 自动清理旧备份，保留最新的10个

生命周期:
- init(): 初始化备份实例
- main(): 持续运行备份检查循环
- cleanup(): 清理资源
"""

import time
import os
import asyncio
import shutil
import fnmatch
import logging
from pathlib import Path
from typing import Optional, List
from datetime import datetime

# 扩展专用日志
logger = logging.getLogger(__name__)


class AutoBackup:
    """自动备份类"""

    def __init__(
        self,
        backup_interval_hours: int = 2,
        backup_dir_name: str = "backups",
        world_dir_name: str = "server/world",
        ignore_patterns: Optional[List[str]] = None
    ):
        """
        初始化自动备份

        Args:
            backup_interval_hours: 备份间隔时间（小时）
            backup_dir_name: 备份目录名
            world_dir_name: 世界目录名
            ignore_patterns: 要忽略的文件/目录模式列表
        """
        self.backup_interval = backup_interval_hours * 3600
        self.last_backup_time: Optional[int] = None

        # 获取项目根目录
        self.project_root = Path(__file__).parent.parent.parent.resolve()

        # 设置路径
        self.backup_dir = self.project_root / backup_dir_name
        self.world_path = self.project_root / world_dir_name

        # 设置忽略模式
        default_ignore = ["session.lock", "*.tmp", "*.lock", "logs/debug/*", "crash-reports/*"]
        self.ignore_patterns = ignore_patterns if ignore_patterns else default_ignore

        # 确保目录存在
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"备份目录: {self.backup_dir}")
        logger.info(f"世界目录: {self.world_path}")
        logger.info(f"忽略模式: {self.ignore_patterns}")

    def _should_ignore(self, path: Path, base_path: Path) -> bool:
        """判断文件/目录是否应该被忽略"""
        try:
            rel_path = path.relative_to(base_path)
            rel_path_str = str(rel_path).replace('\\', '/')

            for pattern in self.ignore_patterns:
                pattern = pattern.replace('\\', '/')

                if fnmatch.fnmatch(rel_path_str, pattern):
                    return True

                if pattern.endswith('/*'):
                    dir_pattern = pattern[:-2]
                    if rel_path_str.startswith(dir_pattern + '/'):
                        return True

            return False

        except ValueError:
            logger.warning(f"无法计算相对路径: {path}")
            return False

    def _copy_with_ignore(self, src: Path, dst: Path, base_path: Path = None):
        """使用自定义逻辑复制文件/目录，忽略指定模式"""
        if base_path is None:
            base_path = self.world_path

        if not src.exists():
            logger.warning(f"源路径不存在: {src}")
            return

        if self._should_ignore(src, base_path):
            return

        if src.is_file():
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            except PermissionError as e:
                if "session.lock" in str(src) or ".lock" in src.name:
                    logger.debug(f"跳过锁文件: {src.name}")
                else:
                    logger.error(f"复制文件时权限错误: {src.name} - {e}")
            except Exception as e:
                logger.error(f"复制文件时出错: {src.name} - {e}")

        elif src.is_dir():
            dst.mkdir(exist_ok=True)

            for item in src.iterdir():
                item_dst = dst / item.name
                self._copy_with_ignore(item, item_dst, base_path)

    def _is_valid_timestamp_dir(self, dir_name: str) -> bool:
        """验证目录名是否为有效的时间戳格式"""
        if len(dir_name) not in [10, 13]:
            return False

        if not dir_name.isdigit():
            return False

        try:
            timestamp = int(dir_name)
            return 1000000000 < timestamp < 2000000000
        except ValueError:
            return False

    async def get_latest_backup_time(self) -> Optional[int]:
        """获取最新备份的时间戳"""
        if not self.backup_dir.exists():
            logger.warning("备份目录不存在")
            return None

        try:
            backup_dirs = [d.name for d in self.backup_dir.iterdir() if d.is_dir()]
            valid_backups = [
                dir_name for dir_name in backup_dirs
                if self._is_valid_timestamp_dir(dir_name)
            ]

            if not valid_backups:
                logger.info("未找到有效备份")
                return None

            latest_backup = max(valid_backups, key=int)
            latest_time = int(latest_backup)

            backup_date = datetime.fromtimestamp(latest_time)
            logger.info(f"最新备份时间: {backup_date.strftime('%Y-%m-%d %H:%M:%S')}")

            return latest_time

        except Exception as e:
            logger.error(f"获取最新备份时出错: {e}")
            return None

    def _should_backup(self) -> bool:
        """判断是否需要备份"""
        if self.last_backup_time is None:
            logger.info("首次备份或未找到有效备份")
            return True

        current_time = int(time.time())
        time_since_last_backup = current_time - self.last_backup_time

        if time_since_last_backup >= self.backup_interval:
            hours = time_since_last_backup / 3600
            logger.info(f"距离上次备份已过去 {hours:.1f} 小时，需要备份")
            return True
        else:
            remaining = (self.backup_interval - time_since_last_backup) / 60
            logger.info(f"无需备份，距离下次备份还有 {remaining:.0f} 分钟")
            return False

    async def create_backup(self) -> bool:
        """创建备份"""
        current_time = int(time.time())
        backup_target_dir = self.backup_dir / str(current_time)

        if not self.world_path.exists():
            logger.error(f"世界目录不存在: {self.world_path}")
            return False

        world_items = list(self.world_path.iterdir())
        if not world_items:
            logger.warning(f"世界目录为空: {self.world_path}")
            return False

        logger.info(f"开始备份到: {backup_target_dir}")
        logger.info(f"世界目录内容数量: {len(world_items)}")

        try:
            if backup_target_dir.exists():
                logger.warning(f"备份目录已存在，删除后重新创建: {backup_target_dir}")
                shutil.rmtree(backup_target_dir, ignore_errors=True)

            backup_target_dir.mkdir(parents=True, exist_ok=True)

            total_files = 0
            total_dirs = 0

            for item in self.world_path.iterdir():
                item_dst = backup_target_dir / item.name

                if self._should_ignore(item, self.world_path):
                    logger.info(f"忽略: {item.name}")
                    continue

                if item.is_file():
                    self._copy_with_ignore(item, item_dst, self.world_path)
                    total_files += 1
                elif item.is_dir():
                    self._copy_with_ignore(item, item_dst, self.world_path)
                    total_dirs += 1

            logger.info(f"复制完成: {total_files} 个文件, {total_dirs} 个目录")

            backup_items = list(backup_target_dir.iterdir())
            if not backup_items:
                logger.error("备份目录为空，没有复制任何文件")
                shutil.rmtree(backup_target_dir, ignore_errors=True)
                return False

            # 记录备份信息
            backup_info = backup_target_dir / "backup_info.txt"
            try:
                backup_size = self._get_directory_size(backup_target_dir)
                with open(backup_info, 'w', encoding='utf-8') as f:
                    f.write(f"备份创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"原始世界路径: {self.world_path}\n")
                    f.write(f"备份间隔: {self.backup_interval/3600} 小时\n")
                    f.write(f"忽略的文件模式: {', '.join(self.ignore_patterns)}\n")
                    f.write(f"备份大小: {backup_size / (1024*1024):.2f} MB\n")
                    f.write(f"文件数量: {total_files}\n")
                    f.write(f"目录数量: {total_dirs}\n")
            except Exception as e:
                logger.warning(f"创建备份信息文件失败: {e}")

            if self._validate_backup(backup_target_dir):
                backup_size_mb = backup_size / (1024*1024)
                logger.info(f"备份成功: {backup_target_dir} ({backup_size_mb:.2f} MB)")
                return True
            else:
                logger.error(f"备份验证失败: {backup_target_dir}")
                shutil.rmtree(backup_target_dir, ignore_errors=True)
                return False

        except Exception as e:
            logger.error(f"备份失败: {e}", exc_info=True)
            if backup_target_dir.exists():
                shutil.rmtree(backup_target_dir, ignore_errors=True)
            return False

    def _get_directory_size(self, path: Path) -> int:
        """计算目录大小"""
        total = 0

        try:
            for dirpath, dirnames, filenames in os.walk(path):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    try:
                        if os.path.exists(filepath):
                            total += os.path.getsize(filepath)
                    except (OSError, PermissionError):
                        continue

            return total
        except Exception as e:
            logger.error(f"计算目录大小时出错: {e}")
            return 0

    def _validate_backup(self, backup_dir: Path) -> bool:
        """验证备份是否有效"""
        try:
            items = list(backup_dir.iterdir())
            if not items:
                logger.warning("备份目录为空")
                return False

            logger.info("备份目录内容:")
            for i, item in enumerate(items[:10]):
                if item.is_file():
                    size = item.stat().st_size / 1024
                    logger.info(f"  {item.name} ({size:.1f} KB)")
                else:
                    item_count = len(list(item.iterdir()))
                    logger.info(f"  {item.name}/ ({item_count} 个项目)")

            if len(items) > 10:
                logger.info(f"  ... 还有 {len(items) - 10} 个项目")

            return len(items) > 0

        except Exception as e:
            logger.error(f"备份验证出错: {e}")
            return False

    async def cleanup_old_backups(self, keep_count: int = 10):
        """清理旧的备份，只保留指定数量的最新备份"""
        try:
            backup_dirs = [d for d in self.backup_dir.iterdir() if d.is_dir()]
            valid_backups = [
                d for d in backup_dirs
                if self._is_valid_timestamp_dir(d.name)
            ]

            if len(valid_backups) <= keep_count:
                return

            sorted_backups = sorted(valid_backups, key=lambda d: int(d.name))
            to_delete = sorted_backups[:-keep_count]

            deleted_count = 0
            for backup_dir in to_delete:
                try:
                    dir_size = self._get_directory_size(backup_dir) / (1024*1024)
                    shutil.rmtree(backup_dir)
                    logger.info(f"删除旧备份: {backup_dir.name} ({dir_size:.1f} MB)")
                    deleted_count += 1
                except Exception as e:
                    logger.error(f"删除备份 {backup_dir.name} 失败: {e}")

            if deleted_count > 0:
                logger.info(f"清理完成，删除了 {deleted_count} 个旧备份")

        except Exception as e:
            logger.error(f"清理旧备份时出错: {e}")

    async def run_backup_cycle(self):
        """执行备份检查循环"""
        try:
            logger.info("=" * 50)
            logger.info("开始备份检查")
            logger.info("=" * 50)

            self.last_backup_time = await self.get_latest_backup_time()

            if self._should_backup():
                logger.info("开始创建备份...")
                if await self.create_backup():
                    self.last_backup_time = int(time.time())
                    logger.info("备份完成")
                    await self.cleanup_old_backups()
                else:
                    logger.error("备份创建失败")
            else:
                logger.info("当前无需备份")

            logger.info("备份检查完成")
            logger.info("=" * 50)

        except Exception as e:
            logger.error(f"备份周期执行出错: {e}", exc_info=True)

    async def run_continuous(self, check_interval_seconds: int = 10):
        """
        持续运行备份检查

        Args:
            check_interval_seconds: 检查间隔（秒），默认10秒检查一次
        """
        logger.info(
            f"开始持续备份检查，备份间隔: {self.backup_interval/3600:.0f}小时，"
            f"检查间隔: {check_interval_seconds} 秒"
        )

        try:
            while True:
                await self.run_backup_cycle()
                logger.info(f"等待 {check_interval_seconds} 秒后再次检查...")
                await asyncio.sleep(check_interval_seconds)
        except asyncio.CancelledError:
            logger.info("备份任务被取消")
        except Exception as e:
            logger.error(f"运行出错: {e}")


# ============ 扩展接口 ============

_backup_instance: Optional[AutoBackup] = None


def init():
    """初始化扩展"""
    global _backup_instance

    _backup_instance = AutoBackup(
        backup_interval_hours=2,
        backup_dir_name="backups",
        world_dir_name="server/world",
        ignore_patterns=[
            "session.lock",
            "*.tmp",
            "*.lock",
            "logs/debug/*",
            "crash-reports/*",
        ]
    )

    logger.info("自动备份扩展初始化完成")


async def main():
    """主函数 - 持续运行备份检查"""
    global _backup_instance

    if _backup_instance is None:
        init()

    # 每10秒检查一次，每2小时备份一次
    await _backup_instance.run_continuous(check_interval_seconds=3600)


def cleanup():
    """清理函数"""
    global _backup_instance
    logger.info("自动备份扩展已清理")
    _backup_instance = None