# . / yasl / event_bus / core.py
"""
事件总线核心模块

包含 EventBus 核心类和相关数据类
"""

import asyncio
import threading
import inspect
import os
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Callable, Dict, List, Any, Optional, TypeVar, Union
from dataclasses import dataclass, field
from contextlib import contextmanager
from enum import Enum

logger = logging.getLogger(__name__)

T = TypeVar("T")


class EventPriority(Enum):
    """事件处理器优先级"""
    HIGHEST = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    LOWEST = 4


@dataclass
class EventMessage:
    """事件消息容器"""
    event_name: str
    message_contained: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def get(self, key: str, default: Any = None) -> Any:
        """安全获取消息内容"""
        return self.message_contained.get(key, default)
    
    def __str__(self) -> str:
        return f"EventMessage(event_name={self.event_name}, timestamp={self.timestamp})"


@dataclass
class HandlerInfo:
    """处理器信息"""
    callback: Callable
    is_async: bool
    priority: int


class EventBusError(Exception):
    """事件总线错误基类"""
    pass


class EventBus:
    """事件总线，支持同步和异步事件处理"""
    
    def __init__(
        self, 
        max_workers: Optional[int] = None,
        error_handler: Optional[Callable[[Exception, EventMessage], None]] = None,
        enable_metrics: bool = False
    ) -> None:
        """
        初始化事件总线
        
        Args:
            max_workers: 线程池最大工作线程数
            error_handler: 错误处理器
            enable_metrics: 是否启用性能指标
        """
        self._lock = threading.RLock()
        self._async_lock = asyncio.Lock()
        
        # 存储事件订阅者
        self._sync_subscribers: Dict[str, List[HandlerInfo]] = {}
        self._async_subscribers: Dict[str, List[HandlerInfo]] = {}
        
        # 事件过滤器
        self._filters: Dict[str, List[Callable[[EventMessage], bool]]] = {}
        
        # 事件组 - 用于批量处理
        self._event_groups: Dict[str, List[str]] = {}
        
        # 配置线程池
        mw = self._get_max_workers(max_workers)
        self._executor = ThreadPoolExecutor(max_workers=mw, thread_name_prefix="EventBus")
        
        # 错误处理器
        self._error_handler = error_handler or self._default_error_handler
        
        # 性能指标
        self._enable_metrics = enable_metrics
        if enable_metrics:
            self._metrics: Dict[str, Any] = {
                "events_published": 0,
                "handlers_executed": 0,
                "errors_occurred": 0,
                "event_times": {},
                "handler_times": {}
            }
        
        # 缓存已注册的事件处理器列表（用于优化）
        self._handlers_cache: Dict[str, tuple] = {}
        self._cache_dirty = True
    
    def _get_max_workers(self, max_workers: Optional[int]) -> int:
        """获取最大工作线程数 - 优化为更合理的默认值"""
        if max_workers is not None and max_workers > 0:
            return max_workers
        
        try:
            mw_env = os.environ.get("EVENT_BUS_MAX_WORKERS")
            if mw_env:
                return max(int(mw_env), 1)
        except (ValueError, TypeError):
            pass
        
        # 默认值：CPU核心数 + 2（更保守的线程数）
        try:
            import multiprocessing
            cpu_count = multiprocessing.cpu_count()
            return min(cpu_count + 2, 8)  # 最多8个线程
        except:
            return 4  # 默认4个线程
    
    def _default_error_handler(self, exc: Exception, event_message: EventMessage) -> None:
        """默认错误处理器"""
        logger.error(
            f"Error processing event '{event_message.event_name}': {exc}",
            exc_info=True,
            extra={"event": event_message.event_name}
        )
    
    def _invalidate_cache(self) -> None:
        """使缓存失效"""
        self._cache_dirty = True
    
    def _update_handlers_cache(self) -> None:
        """更新处理器缓存"""
        if not self._cache_dirty:
            return
            
        with self._lock:
            self._handlers_cache.clear()
            
            # 合并同步和异步处理器
            all_events = set(self._sync_subscribers.keys()) | set(self._async_subscribers.keys())
            
            for event_name in all_events:
                sync_handlers = [
                    info.callback for info in self._sync_subscribers.get(event_name, [])
                ]
                async_handlers = [
                    info.callback for info in self._async_subscribers.get(event_name, [])
                ]
                
                # 存储为元组（不可变）
                self._handlers_cache[event_name] = (
                    tuple(sync_handlers),
                    tuple(async_handlers)
                )
            
            self._cache_dirty = False
    
    def subscribe(
        self, 
        event_name: str, 
        callback: Callable[[EventMessage], Any], 
        priority: Union[EventPriority, int] = EventPriority.NORMAL,
        group: Optional[str] = None
    ) -> Callable[[], bool]:
        """
        订阅事件
        
        Args:
            event_name: 事件名称
            callback: 回调函数
            priority: 优先级
            group: 事件组名称（可选）
            
        Returns:
            取消订阅函数
        """
        if not callable(callback):
            raise TypeError("Callback must be callable")
        
        # 转换优先级
        if isinstance(priority, EventPriority):
            priority_value = priority.value
        else:
            priority_value = int(priority)
        
        is_async = inspect.iscoroutinefunction(callback)
        handler_info = HandlerInfo(callback=callback, is_async=is_async, priority=priority_value)
        
        with self._lock:
            if is_async:
                subscribers = self._async_subscribers.setdefault(event_name, [])
            else:
                subscribers = self._sync_subscribers.setdefault(event_name, [])
            
            # 按优先级插入（数值越小优先级越高）
            subscribers.append(handler_info)
            subscribers.sort(key=lambda x: x.priority)
            
            # 注册到事件组
            if group:
                self._event_groups.setdefault(group, []).append(event_name)
            
            # 使缓存失效
            self._invalidate_cache()
        
        def unsubscribe() -> bool:
            """取消订阅"""
            with self._lock:
                if is_async:
                    subscribers = self._async_subscribers.get(event_name)
                else:
                    subscribers = self._sync_subscribers.get(event_name)
                
                if not subscribers:
                    return False
                
                # 找到并移除处理器
                for i, info in enumerate(subscribers):
                    if info.callback is callback:
                        subscribers.pop(i)
                        self._invalidate_cache()
                        return True
                return False
        
        return unsubscribe
    
    def on(self, event_name: str, priority: Union[EventPriority, int] = EventPriority.NORMAL, group: Optional[str] = None):
        """
        装饰器语法糖，用于订阅事件
        
        Args:
            event_name: 事件名称
            priority: 优先级
            group: 事件组名称（可选）
        """
        def decorator(callback: Callable[[EventMessage], Any]) -> Callable[[EventMessage], Any]:
            self.subscribe(event_name, callback, priority, group)
            return callback
        return decorator
    
    def add_filter(self, event_name: str, filter_func: Callable[[EventMessage], bool]) -> None:
        """
        添加事件过滤器
        
        Args:
            event_name: 事件名称
            filter_func: 过滤函数，返回True表示允许事件通过
        """
        if not callable(filter_func):
            raise TypeError("Filter function must be callable")
        
        with self._lock:
            self._filters.setdefault(event_name, []).append(filter_func)
    
    def remove_filter(self, event_name: str, filter_func: Callable[[EventMessage], bool]) -> bool:
        """移除事件过滤器"""
        with self._lock:
            filters = self._filters.get(event_name)
            if not filters:
                return False
            
            try:
                filters.remove(filter_func)
                return True
            except ValueError:
                return False
    
    def _check_filters(self, event_name: str, event_message: EventMessage) -> bool:
        """检查事件是否通过所有过滤器"""
        with self._lock:
            filters = self._filters.get(event_name, [])
        
        for filter_func in filters:
            try:
                if not filter_func(event_message):
                    return False
            except Exception as e:
                logger.warning(f"Filter function failed for event '{event_name}': {e}")
                # 过滤器失败时默认允许通过
                continue
        
        return True
    
    def _prepare_event_message(self, event_name: str, **payload: Any) -> EventMessage:
        """创建事件消息容器"""
        return EventMessage(
            event_name=event_name,
            message_contained=payload
        )
    
    async def _run_async_handler(self, handler: Callable, event_message: EventMessage) -> None:
        """运行异步处理器"""
        start_time = datetime.now()
        try:
            await handler(event_message)
            if self._enable_metrics:
                elapsed = (datetime.now() - start_time).total_seconds()
                with self._lock:
                    self._metrics["handlers_executed"] += 1
                    handler_name = getattr(handler, '__name__', repr(handler))
                    if handler_name not in self._metrics["handler_times"]:
                        self._metrics["handler_times"][handler_name] = {"count": 0, "total_time": 0}
                    self._metrics["handler_times"][handler_name]["count"] += 1
                    self._metrics["handler_times"][handler_name]["total_time"] += elapsed
        except Exception as e:
            if self._enable_metrics:
                with self._lock:
                    self._metrics["errors_occurred"] += 1
            self._error_handler(e, event_message)
    
    def _run_sync_handler(self, handler: Callable, event_message: EventMessage) -> None:
        """运行同步处理器"""
        start_time = datetime.now()
        try:
            handler(event_message)
            if self._enable_metrics:
                elapsed = (datetime.now() - start_time).total_seconds()
                with self._lock:
                    self._metrics["handlers_executed"] += 1
                    handler_name = getattr(handler, '__name__', repr(handler))
                    if handler_name not in self._metrics["handler_times"]:
                        self._metrics["handler_times"][handler_name] = {"count": 0, "total_time": 0}
                    self._metrics["handler_times"][handler_name]["count"] += 1
                    self._metrics["handler_times"][handler_name]["total_time"] += elapsed
        except Exception as e:
            if self._enable_metrics:
                with self._lock:
                    self._metrics["errors_occurred"] += 1
            self._error_handler(e, event_message)
    
    async def publish_async(self, event_name: str, **message_contained: Any) -> None:
        """异步发布事件"""
        start_time = datetime.now() if self._enable_metrics else None
        
        event_message = self._prepare_event_message(event_name, **message_contained)
        
        # 检查过滤器
        if not self._check_filters(event_name, event_message):
            return
        
        # 使用缓存的处理器列表（如果可用）
        self._update_handlers_cache()
        
        with self._lock:
            cached = self._handlers_cache.get(event_name)
            if cached:
                sync_handlers, async_handlers = cached
            else:
                sync_handlers = []
                async_handlers = []
        
        # 运行异步处理器
        if async_handlers:
            tasks = [
                self._run_async_handler(handler, event_message) 
                for handler in async_handlers
            ]
            await asyncio.gather(*tasks, return_exceptions=True)
        
        # 运行同步处理器（在线程池中）
        for handler in sync_handlers:
            try:
                self._executor.submit(self._run_sync_handler, handler, event_message)
            except Exception as e:
                logger.error(f"Failed to submit sync handler for event '{event_name}': {e}")
        
        if self._enable_metrics and start_time:
            with self._lock:
                self._metrics["events_published"] += 1
                elapsed = (datetime.now() - start_time).total_seconds()
                if event_name not in self._metrics["event_times"]:
                    self._metrics["event_times"][event_name] = {"count": 0, "total_time": 0}
                self._metrics["event_times"][event_name]["count"] += 1
                self._metrics["event_times"][event_name]["total_time"] += elapsed
    
    def publish(self, event_name: str, **message_contained: Any) -> None:
        """
        同步发布事件（向后兼容）
        
        注意：如果在没有事件循环的线程中调用，会使用同步版本
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果事件循环正在运行，创建异步任务
                asyncio.create_task(self.publish_async(event_name, **message_contained))
            else:
                # 否则同步运行
                loop.run_until_complete(self.publish_async(event_name, **message_contained))
        except RuntimeError:
            # 如果没有事件循环或不在主线程中，使用同步版本
            logger.debug("No event loop found, using sync publish")
            self.publish_sync(event_name, **message_contained)
        except Exception as e:
            logger.error(f"Failed to publish event '{event_name}': {e}")
            # 降级到同步发布
            self.publish_sync(event_name, **message_contained)
    
    def publish_sync(self, event_name: str, **message_contained: Any) -> None:
        """同步发布事件（阻塞）"""
        event_message = self._prepare_event_message(event_name, **message_contained)
        
        # 检查过滤器
        if not self._check_filters(event_name, event_message):
            return
        
        # 获取处理器快照
        with self._lock:
            sync_handlers = [
                info.callback for info in self._sync_subscribers.get(event_name, [])
            ]
        
        # 同步运行处理器
        for handler in sync_handlers:
            self._run_sync_handler(handler, event_message)
    
    # 简化的特定事件发布方法
    async def emit_async(self, event_name: str, **message_contained: Any) -> None:
        """异步emit的别名"""
        await self.publish_async(event_name, **message_contained)
    
    def emit(self, event_name: str, **message_contained: Any) -> None:
        """emit的别名，保持同步"""
        self.publish(event_name, **message_contained)
    
    # 快捷方法
    async def player_join_async(self, player_id: str, player_name: str, **extra_data: Any) -> None:
        """异步玩家加入事件快捷方法"""
        await self.publish_async(
            "player_join", 
            player_id=player_id, 
            player_name=player_name, 
            **extra_data
        )
    
    async def player_chat_async(
        self,
        player_name: str,
        message: str,
        timestamp: Optional[str] = None,
        server_time: str = "",
        source: str = "server",
        **extra_data: Any,
    ) -> None:
        """异步玩家聊天事件"""
        await self.publish_async(
            "player_chat",
            player_name=player_name,
            message=message,
            timestamp=timestamp or datetime.now().isoformat(),
            server_time=server_time,
            source=source,
            **extra_data,
        )
    
    def has_subscribers(self, event_name: str) -> bool:
        """检查事件是否有订阅者"""
        with self._lock:
            sync_count = len(self._sync_subscribers.get(event_name, []))
            async_count = len(self._async_subscribers.get(event_name, []))
            return (sync_count + async_count) > 0
    
    def get_subscriber_count(self, event_name: str) -> int:
        """获取事件订阅者数量"""
        with self._lock:
            sync_count = len(self._sync_subscribers.get(event_name, []))
            async_count = len(self._async_subscribers.get(event_name, []))
            return sync_count + async_count
    
    def get_all_events(self) -> List[str]:
        """获取所有已注册的事件名称"""
        with self._lock:
            return list(set(
                list(self._sync_subscribers.keys()) + 
                list(self._async_subscribers.keys())
            ))
    
    def get_event_groups(self) -> Dict[str, List[str]]:
        """获取所有事件组"""
        with self._lock:
            return self._event_groups.copy()
    
    async def publish_group_async(self, group: str, **message_contained: Any) -> None:
        """异步发布到事件组中的所有事件"""
        with self._lock:
            events = self._event_groups.get(group, []).copy()
        
        tasks = []
        for event_name in events:
            tasks.append(self.publish_async(event_name, **message_contained))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        if not self._enable_metrics:
            raise EventBusError("Metrics are not enabled")
        
        with self._lock:
            metrics = self._metrics.copy()
            
            # 计算平均时间
            if metrics["events_published"] > 0:
                event_times = {}
                for event_name, data in metrics["event_times"].items():
                    event_times[event_name] = {
                        "count": data["count"],
                        "total_time": data["total_time"],
                        "avg_time": data["total_time"] / data["count"] if data["count"] > 0 else 0
                    }
                metrics["event_times"] = event_times
            
            # 处理程序时间
            handler_times = {}
            for handler_name, data in metrics.get("handler_times", {}).items():
                handler_times[handler_name] = {
                    "count": data["count"],
                    "total_time": data["total_time"],
                    "avg_time": data["total_time"] / data["count"] if data["count"] > 0 else 0
                }
            metrics["handler_times"] = handler_times
            
            return metrics
    
    async def unsubscribe_all_async(self, event_name: str) -> int:
        """异步取消订阅所有处理器"""
        with self._lock:
            sync_count = len(self._sync_subscribers.pop(event_name, []))
            async_count = len(self._async_subscribers.pop(event_name, []))
            self._invalidate_cache()
            return sync_count + async_count
    
    def clear_subscribers(self, event_name: str) -> int:
        """清除指定事件的所有订阅者"""
        with self._lock:
            sync_count = len(self._sync_subscribers.pop(event_name, []))
            async_count = len(self._async_subscribers.pop(event_name, []))
            self._invalidate_cache()
            return sync_count + async_count
    
    async def shutdown_async(self, wait: bool = True, timeout: Optional[float] = None) -> None:
        """异步关闭EventBus"""
        try:
            if timeout:
                self._executor.shutdown(wait=wait, timeout=timeout)
            else:
                self._executor.shutdown(wait=wait)
        except Exception as e:
            logger.error(f"Error shutting down EventBus: {e}")
            if not wait:
                raise
    
    @contextmanager
    def temporary_subscription(
        self, 
        event_name: str, 
        callback: Callable[[EventMessage], Any],
        priority: Union[EventPriority, int] = EventPriority.NORMAL
    ):
        """
        临时订阅上下文管理器
        
        Example:
            with bus.temporary_subscription("test", my_handler):
                bus.publish("test", data="hello")
        """
        unsubscribe = self.subscribe(event_name, callback, priority)
        try:
            yield
        finally:
            unsubscribe()


# 全局EventBus实例
_bus_instance: Optional[EventBus] = None


def get_event_bus(
    max_workers: Optional[int] = None,
    error_handler: Optional[Callable[[Exception, EventMessage], None]] = None,
    reset: bool = False
) -> EventBus:
    """获取或创建全局EventBus实例"""
    global _bus_instance
    
    if reset or _bus_instance is None:
        _bus_instance = EventBus(
            max_workers=max_workers,
            error_handler=error_handler,
            enable_metrics=True  # 默认启用指标收集
        )
    
    return _bus_instance


def set_global_event_bus(bus: EventBus) -> None:
    """设置全局EventBus实例"""
    global _bus_instance
    _bus_instance = bus


# 默认使用全局实例
bus = get_event_bus()
