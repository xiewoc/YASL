# . / yasl / event_bus / __init__.py
"""
YASL 事件总线模块

提供高性能的同步/异步事件处理系统，支持：
- 优先级事件处理
- 事件过滤器
- 性能指标收集
- 事件组和批量处理
"""

from yasl.event_bus.core import (
    EventBus,
    EventMessage,
    EventPriority,
    HandlerInfo,
    EventBusError,
    get_event_bus,
    set_global_event_bus,
    bus,
)
from yasl.event_bus.detectors import (
    CHAT_PATTERN,
    LIFECYCLE_PATTERNS,
    _log_lifecycle_detector,
    _log_chat_detector,
)
from yasl.event_bus.helpers import (
    subscribe,
    on,
    publish_async,
    publish,
    emit_async,
    emit,
    player_join_async,
    player_chat_async,
    start_async,
    done_async,
    stop_async,
    on_start,
    on_done,
    on_stop,
    on_player_chat,
    on_player_join,
    publish_sync,
    has_subscribers,
    get_subscriber_count,
    get_metrics,
    unsubscribe_all_async,
    clear_subscribers,
    shutdown_event_bus_async,
    reset_global_bus,
)

__all__ = [
    # 核心类
    "EventBus",
    "EventMessage",
    "EventPriority",
    "HandlerInfo",
    "EventBusError",
    # 核心函数
    "get_event_bus",
    "set_global_event_bus",
    "bus",
    # 检测器
    "CHAT_PATTERN",
    "LIFECYCLE_PATTERNS",
    "_log_lifecycle_detector",
    "_log_chat_detector",
    # 辅助函数
    "subscribe",
    "on",
    "publish_async",
    "publish",
    "emit_async",
    "emit",
    "player_join_async",
    "player_chat_async",
    "start_async",
    "done_async",
    "stop_async",
    "on_start",
    "on_done",
    "on_stop",
    "on_player_chat",
    "on_player_join",
    "publish_sync",
    "has_subscribers",
    "get_subscriber_count",
    "get_metrics",
    "unsubscribe_all_async",
    "clear_subscribers",
    "shutdown_event_bus_async",
    "reset_global_bus",
]
