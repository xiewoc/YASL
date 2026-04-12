"""
扩展管理器模块
负责加载和管理所有扩展模块

扩展生命周期:
1. init() - 初始化函数，在模块加载后调用
2. main() - 主函数，作为异步任务启动（可选）
3. cleanup() - 清理函数，在卸载扩展时调用

扩展可用的注入变量:
- bus: 事件总线实例
- data_dir: 扩展数据目录路径
- log: 扩展专用日志函数
"""

import importlib
import importlib.util
import inspect
import asyncio
import sys
import traceback
import os
import logging
from pathlib import Path
from typing import Dict, List, Callable, Optional, Any
from datetime import datetime

# 配置日志
logger = logging.getLogger(__name__)

try:
    from yasl.event_bus import bus, subscribe, on, publish_async
    _HAS_EVENT_BUS = True
except ImportError:
    _HAS_EVENT_BUS = False
    bus = None

    def subscribe(*args, **kwargs):
        def dummy():
            pass
        return dummy

    def on(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

    def publish_async(*args, **kwargs):
        async def dummy():
            pass
        return dummy()


class ExtensionManager:
    """
    扩展管理器
    
    支持异步加载、管理和卸载扩展模块。
    提供事件总线集成、依赖注入和生命周期管理。
    """

    def __init__(
        self,
        extensions_dir: str = "extensions",
        enable_events: bool = True,
        debug: bool = False,
    ):
        """
        初始化扩展管理器

        Args:
            extensions_dir: 扩展目录路径
            enable_events: 是否启用事件系统
            debug: 是否启用调试模式
        """
        self.extensions_dir = Path(extensions_dir)
        self.enable_events = enable_events and _HAS_EVENT_BUS
        self.debug = debug

        # 计算 data 目录路径
        self.data_dir = self._get_data_dir()

        # 扩展存储
        self.extensions: Dict[str, dict] = {}
        self.extension_tasks: Dict[str, List[asyncio.Task]] = {}
        self.event_handlers: Dict[str, List[Callable]] = {}

        # 确保目录存在
        self._ensure_directories()

    def _ensure_directories(self):
        """确保扩展目录和数据目录存在"""
        if not self.extensions_dir.exists():
            self.extensions_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"创建扩展目录: {self.extensions_dir}")

        if not self.data_dir.exists():
            self.data_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"创建数据目录: {self.data_dir}")

    def _get_data_dir(self) -> Path:
        """获取扩展数据目录路径"""
        ext_path = Path(self.extensions_dir)

        if ext_path.is_absolute():
            return ext_path.parent / "extensions" / "data"

        return Path("extensions") / "data"

    def log(self, message: str, level: str = "INFO"):
        """
        输出扩展管理器日志

        Args:
            message: 日志消息
            level: 日志级别 (INFO, WARN, ERROR, DEBUG)
        """
        level_map = {
            "INFO": logger.info,
            "WARN": logger.warning,
            "ERROR": logger.error,
            "DEBUG": logger.debug,
        }
        log_func = level_map.get(level, logger.info)
        log_func(message)

    async def load_all_extensions_async(self):
        """异步加载所有扩展模块"""
        if not self.extensions_dir.exists():
            logger.warning(f"扩展目录不存在: {self.extensions_dir}")
            return

        # 查找所有Python扩展文件
        py_files = list(self.extensions_dir.glob("*.py"))
        if not py_files:
            logger.info("扩展目录中没有找到扩展文件")
            return

        logger.info(f"发现 {len(py_files)} 个扩展待加载")

        # 并行加载所有扩展
        load_tasks = []
        for py_file in py_files:
            if py_file.name.startswith("_"):
                continue
            load_tasks.append(self.load_extension_async(py_file))

        await asyncio.gather(*load_tasks, return_exceptions=True)

    async def load_extension_async(self, extension_file: Path):
        """
        异步加载单个扩展模块

        Args:
            extension_file: 扩展文件路径
        """
        extension_name = extension_file.stem

        try:
            if self.debug:
                logger.debug(f"正在加载扩展: {extension_name}")

            # 检查模块是否已加载
            if extension_name in self.extensions:
                logger.warning(f"扩展 '{extension_name}' 已加载")
                return

            # 动态导入模块
            spec = importlib.util.spec_from_file_location(
                f"extensions.{extension_name}", extension_file
            )
            if spec is None:
                logger.error(f"无法创建模块规范: {extension_name}")
                return

            module = importlib.util.module_from_spec(spec)

            # 注入全局变量
            self._inject_module_globals(module, extension_name)

            # 执行模块代码
            spec.loader.exec_module(module)

            # 存储模块信息
            extension_info = {
                "module": module,
                "name": extension_name,
                "file": extension_file,
                "loaded_at": datetime.now(),
                "status": "loaded",
            }

            # 执行初始化
            await self._call_init(module, extension_name, extension_info)

            # 启动主函数
            await self._start_main(module, extension_name, extension_info)

            # 注册事件处理器
            await self._auto_register_handlers_async(module, extension_name)

            # 存储扩展
            self.extensions[extension_name] = extension_info

            logger.info(f"✓ 扩展加载成功: {extension_name}")

        except Exception as e:
            logger.error(f"✗ 扩展加载失败 {extension_name}: {e}")
            if self.debug:
                traceback.print_exc()

    def _inject_module_globals(self, module, extension_name: str):
        """
        向模块注入全局变量

        Args:
            module: 模块对象
            extension_name: 扩展名称
        """
        module_globals = module.__dict__

        # 事件总线相关
        module_globals.update({
            "bus": bus,
            "subscribe": subscribe,
            "on": on,
            "publish_async": publish_async,
            "EventMessage": None,
        })

        # 扩展管理器
        module_globals["extension_manager"] = self

        # 数据目录
        module_globals["data_dir"] = self.data_dir

        # 日志函数
        module_globals["log"] = self._create_extension_log(extension_name)

        # 标准库
        module_globals.update({
            "datetime": datetime,
            "asyncio": asyncio,
            "time": __import__("time"),
            "os": os,
            "Path": Path,
        })

        # 尝试导入 EventMessage
        if _HAS_EVENT_BUS:
            try:
                from yasl.event_bus import EventMessage
                module_globals["EventMessage"] = EventMessage
            except ImportError:
                pass

    def _create_extension_log(self, extension_name: str) -> Callable:
        """
        创建扩展专用日志函数

        Args:
            extension_name: 扩展名称

        Returns:
            日志函数
        """
        ext_logger = logging.getLogger(f"ext.{extension_name}")

        def extension_log(message: str, level: str = "INFO"):
            level_map = {
                "INFO": ext_logger.info,
                "WARN": ext_logger.warning,
                "ERROR": ext_logger.error,
                "DEBUG": ext_logger.debug,
            }
            log_func = level_map.get(level, ext_logger.info)
            log_func(message)

        return extension_log

    async def _call_init(self, module, extension_name: str, extension_info: dict):
        """
        调用扩展的初始化函数

        Args:
            module: 模块对象
            extension_name: 扩展名称
            extension_info: 扩展信息字典
        """
        if not hasattr(module, "init"):
            return

        try:
            if inspect.iscoroutinefunction(module.init):
                await module.init()
            else:
                module.init()

            extension_info["has_init"] = True

            if self.debug:
                logger.debug(f"扩展 '{extension_name}' init() 已调用")

        except Exception as e:
            logger.error(f"扩展 '{extension_name}' init() 出错: {e}")
            if self.debug:
                traceback.print_exc()

    async def _start_main(self, module, extension_name: str, extension_info: dict):
        """
        启动扩展的主函数

        Args:
            module: 模块对象
            extension_name: 扩展名称
            extension_info: 扩展信息字典
        """
        if not hasattr(module, "main"):
            return

        try:
            if inspect.iscoroutinefunction(module.main):
                task = asyncio.create_task(module.main())
            else:
                loop = asyncio.get_event_loop()
                task = loop.run_in_executor(None, module.main)

            self.extension_tasks.setdefault(extension_name, []).append(task)
            extension_info["has_main"] = True
            extension_info["task"] = task

            if self.debug:
                logger.debug(f"扩展 '{extension_name}' main() 已启动")

        except Exception as e:
            logger.error(f"扩展 '{extension_name}' main() 启动出错: {e}")
            if self.debug:
                traceback.print_exc()

    async def _auto_register_handlers_async(self, module, extension_name: str):
        """
        自动注册事件处理器

        Args:
            module: 模块对象
            extension_name: 扩展名称
        """
        if not self.enable_events or not _HAS_EVENT_BUS:
            return

        for name, obj in inspect.getmembers(module):
            if callable(obj) and hasattr(obj, "_event_handler"):
                event_name = obj._event_handler
                unsubscribe = subscribe(event_name, obj)

                self.event_handlers.setdefault(extension_name, []).append({
                    "event": event_name,
                    "handler": name,
                    "unsubscribe": unsubscribe,
                })

                if self.debug:
                    logger.debug(f"  注册事件处理器: {name} -> {event_name}")

    async def unload_extension_async(self, extension_name: str):
        """
        异步卸载扩展

        Args:
            extension_name: 扩展名称
        """
        if extension_name not in self.extensions:
            logger.warning(f"扩展 '{extension_name}' 未找到")
            return

        # 取消注册所有事件处理器
        if extension_name in self.event_handlers:
            for handler_info in self.event_handlers[extension_name]:
                try:
                    handler_info["unsubscribe"]()
                except Exception as e:
                    if self.debug:
                        logger.debug(f"  取消订阅 {handler_info['handler']} 出错: {e}")
            del self.event_handlers[extension_name]

        # 停止任务
        if extension_name in self.extension_tasks:
            for task in self.extension_tasks[extension_name]:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            del self.extension_tasks[extension_name]

        # 调用清理函数
        extension_info = self.extensions[extension_name]
        module = extension_info["module"]

        if hasattr(module, "cleanup"):
            try:
                if inspect.iscoroutinefunction(module.cleanup):
                    await module.cleanup()
                else:
                    module.cleanup()

                if self.debug:
                    logger.debug(f"扩展 '{extension_name}' cleanup() 已调用")

            except Exception as e:
                logger.error(f"扩展 '{extension_name}' cleanup() 出错: {e}")

        # 从内存中移除
        module_name = f"extensions.{extension_name}"
        if module_name in sys.modules:
            del sys.modules[module_name]

        del self.extensions[extension_name]

        logger.info(f"✓ 扩展已卸载: {extension_name}")

    async def reload_extension_async(self, extension_name: str):
        """
        异步重新加载扩展

        Args:
            extension_name: 扩展名称
        """
        if extension_name not in self.extensions:
            logger.warning(f"无法重载 '{extension_name}': 未加载")
            return

        extension_info = self.extensions[extension_name]
        extension_file = extension_info["file"]

        logger.info(f"正在重载扩展: {extension_name}")

        await self.unload_extension_async(extension_name)
        await self.load_extension_async(extension_file)

    def list_extensions(self) -> List[str]:
        """列出所有已加载的扩展"""
        return list(self.extensions.keys())

    def get_extension_info(self, extension_name: str) -> Optional[Dict[str, Any]]:
        """
        获取扩展信息

        Args:
            extension_name: 扩展名称

        Returns:
            扩展信息字典，如果扩展不存在则返回 None
        """
        if extension_name not in self.extensions:
            return None

        info = self.extensions[extension_name].copy()
        info.pop("module", None)
        info.pop("task", None)

        return info

    async def broadcast_event_async(self, event_name: str, **kwargs):
        """
        异步向所有扩展广播事件

        Args:
            event_name: 事件名称
            **kwargs: 事件参数
        """
        if not self.enable_events:
            return

        for ext_name, handlers in self.event_handlers.items():
            for handler_info in handlers:
                if handler_info["event"] == event_name:
                    if self.debug:
                        logger.debug(
                            f"广播事件 {event_name} 到 {ext_name}.{handler_info['handler']}"
                        )

    async def shutdown_async(self):
        """异步关闭扩展管理器，卸载所有扩展"""
        logger.info("正在关闭扩展管理器...")

        unload_tasks = [
            self.unload_extension_async(name)
            for name in list(self.extensions.keys())
        ]

        await asyncio.gather(*unload_tasks, return_exceptions=True)

        logger.info("扩展管理器已关闭")


def event_handler(event_name: str):
    """
    装饰器：将函数标记为事件处理器

    Args:
        event_name: 要订阅的事件名称

    使用示例:
        @event_handler('player_join')
        async def on_player_join(event_message):
            print(f"玩家加入: {event_message.message_contained['player_name']}")
    """

    def decorator(func):
        func._event_handler = event_name
        return func

    return decorator


# 全局扩展管理器实例
_manager_instance: Optional[ExtensionManager] = None


def get_extension_manager(
    extensions_dir: str = "extensions",
    enable_events: bool = True,
    debug: bool = False
) -> ExtensionManager:
    """
    获取全局扩展管理器实例（单例模式）

    Args:
        extensions_dir: 扩展目录路径
        enable_events: 是否启用事件系统
        debug: 是否启用调试模式

    Returns:
        ExtensionManager 实例
    """
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = ExtensionManager(
            extensions_dir=extensions_dir,
            enable_events=enable_events,
            debug=debug
        )
    return _manager_instance


def reset_extension_manager(
    extensions_dir: str = "extensions",
    enable_events: bool = True,
    debug: bool = False
) -> ExtensionManager:
    """
    重置并获取全局扩展管理器实例

    Args:
        extensions_dir: 扩展目录路径
        enable_events: 是否启用事件系统
        debug: 是否启用调试模式

    Returns:
        新的 ExtensionManager 实例
    """
    global _manager_instance
    _manager_instance = ExtensionManager(
        extensions_dir=extensions_dir,
        enable_events=enable_events,
        debug=debug
    )
    return _manager_instance