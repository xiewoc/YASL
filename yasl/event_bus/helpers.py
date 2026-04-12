# . / yasl / event_bus / helpers.py
"""
事件总线辅助函数模块

包含全局便捷函数，用于订阅和发布事件
"""

from typing import Callable, Any, Optional, Dict, List, Union, TypeVar
from yasl.event_bus.core import (
    EventMessage,
    EventPriority,
    bus,
)

# 类型变量
T = TypeVar("T")


# 全局函数（向后兼容）
def subscribe(
    event_name: str, 
    callback: Callable[[EventMessage], Any],
    priority: Union[EventPriority, int] = EventPriority.NORMAL
) -> Callable[[], bool]:
    """订阅全局事件总线的事件"""
    return bus.subscribe(event_name, callback, priority)


def on(event_name: str, priority: Union[EventPriority, int] = EventPriority.NORMAL):
    """全局装饰器语法糖"""
    def decorator(callback: Callable[[EventMessage], Any]) -> Callable[[EventMessage], Any]:
        bus.subscribe(event_name, callback, priority)
        return callback
    return decorator


async def publish_async(event_name: str, **message_contained: Any) -> None:
    """异步发布事件"""
    await bus.publish_async(event_name, **message_contained)


def publish(event_name: str, **message_contained: Any) -> None:
    """同步发布事件 - 自动处理异步"""
    bus.publish(event_name, **message_contained)


async def emit_async(event_name: str, **message_contained: Any) -> None:
    """异步emit"""
    await bus.emit_async(event_name, **message_contained)


def emit(event_name: str, **message_contained: Any) -> None:
    """同步emit（向后兼容）"""
    bus.emit(event_name, **message_contained)


# 快捷事件发布函数
async def player_join_async(player_id: str, player_name: str, **extra_data: Any) -> None:
    """异步玩家加入事件"""
    await bus.player_join_async(player_id, player_name, **extra_data)


async def player_chat_async(
    player_name: str,
    message: str,
    timestamp: Optional[str] = None,
    server_time: str = "",
    source: str = "server",
    **extra_data: Any,
) -> None:
    """异步发布玩家聊天事件"""
    await bus.player_chat_async(
        player_name=player_name,
        message=message,
        timestamp=timestamp,
        server_time=server_time,
        source=source,
        **extra_data,
    )


async def start_async(
    phase: str = "started",
    time: Optional[str] = None,
    source: str = "",
    message: str = "",
    **extra_data: Any,
) -> None:
    """异步发布启动相关事件"""
    await bus.publish_async(
        "start",
        phase=phase,
        time=time or "",
        source=source,
        message=message,
        **extra_data,
    )


async def done_async(
    time_taken: Optional[str] = None,
    time: Optional[str] = None,
    source: str = "",
    message: str = "",
    **extra_data: Any,
) -> None:
    """异步发布完成事件"""
    await bus.publish_async(
        "done",
        time_taken=time_taken or "",
        time=time or "",
        source=source,
        message=message,
        **extra_data,
    )


async def stop_async(
    time: Optional[str] = None, 
    source: str = "", 
    message: str = "", 
    **extra_data: Any
) -> None:
    """异步发布停止事件"""
    await bus.publish_async(
        "stop", time=time or "", source=source, message=message, **extra_data
    )


# 装饰器函数
def on_start(priority: Union[EventPriority, int] = EventPriority.NORMAL):
    """装饰器：订阅 `start` 事件。"""
    return on("start", priority)


def on_done(priority: Union[EventPriority, int] = EventPriority.NORMAL):
    """装饰器：订阅 `done` 事件。"""
    return on("done", priority)


def on_stop(priority: Union[EventPriority, int] = EventPriority.NORMAL):
    """装饰器：订阅 `stop` 事件。"""
    return on("stop", priority)


def on_player_chat(priority: Union[EventPriority, int] = EventPriority.NORMAL):
    """装饰器：订阅 `player_chat` 事件。"""
    return on("player_chat", priority)


def on_player_join(priority: Union[EventPriority, int] = EventPriority.NORMAL):
    """装饰器：订阅 `player_join` 事件。"""
    return on("player_join", priority)


# 同步函数（保持向后兼容）
def publish_sync(event_name: str, **message_contained: Any) -> None:
    bus.publish_sync(event_name, **message_contained)


def has_subscribers(event_name: str) -> bool:
    return bus.has_subscribers(event_name)


def get_subscriber_count(event_name: str) -> int:
    """获取事件订阅者数量"""
    return bus.get_subscriber_count(event_name)


def get_metrics() -> Dict[str, Any]:
    """获取性能指标"""
    return bus.get_metrics()


async def unsubscribe_all_async(event_name: str) -> int:
    """异步取消订阅所有处理器"""
    return await bus.unsubscribe_all_async(event_name)


def clear_subscribers(event_name: str) -> int:
    """清除指定事件的所有订阅者"""
    return bus.clear_subscribers(event_name)


async def shutdown_event_bus_async(wait: bool = True, timeout: Optional[float] = None) -> None:
    """异步关闭全局事件总线"""
    await bus.shutdown_async(wait, timeout)


def reset_global_bus(
    max_workers: Optional[int] = None,
    error_handler: Optional[Callable[[Exception, EventMessage], None]] = None
):
    """重置全局事件总线"""
    from yasl.event_bus.core import get_event_bus
    return get_event_bus(max_workers, error_handler, reset=True)
