"""
事件检测器模块

包含日志事件检测器，用于识别 Minecraft 服务器日志中的特定事件
"""

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# 从公共模块导入正则表达式
from yasl.utils import PLAYER_PATTERNS, SERVER_PATTERNS

# 聊天消息正则表达式（向后兼容）
CHAT_PATTERN = PLAYER_PATTERNS["chat"]

# 生命周期相关正则（向后兼容）
LIFECYCLE_PATTERNS = {
    "done": SERVER_PATTERNS["done"],
    "preparing": SERVER_PATTERNS["preparing"],
    "starting": SERVER_PATTERNS["starting"],
    "stopping": SERVER_PATTERNS["stopping"],
    "started": SERVER_PATTERNS["started"],
}


async def _log_lifecycle_detector(event_message) -> None:
    """异步监听日志事件，识别生命周期事件"""
    try:
        level = event_message.get("level", "")
        source = event_message.get("source", "")
        message = event_message.get("message", "")
        time_field = event_message.get("time", "")

        if "minecraft" not in (source or "").lower() and level != "INFO":
            return

        # done
        m = LIFECYCLE_PATTERNS["done"].search(message)
        if m:
            time_taken = m.group(1)
            # 延迟导入以避免循环依赖
            from yasl.event_bus.core import bus
            await bus.emit_async(
                "done",
                time_taken=time_taken,
                time=time_field,
                source=source,
                message=message,
            )
            return

        # starting
        if LIFECYCLE_PATTERNS["starting"].search(message):
            from yasl.event_bus.core import bus
            await bus.emit_async(
                "start",
                phase="starting",
                time=time_field,
                source=source,
                message=message,
            )
            return

        # started
        if LIFECYCLE_PATTERNS["started"].search(message):
            from yasl.event_bus.core import bus
            await bus.emit_async(
                "start",
                phase="started",
                time=time_field,
                source=source,
                message=message,
            )
            return

        # stopping
        if LIFECYCLE_PATTERNS["stopping"].search(message):
            from yasl.event_bus.core import bus
            await bus.emit_async(
                "stop", time=time_field, source=source, message=message
            )
            return

    except Exception as e:
        logger.error(f"Error in _log_lifecycle_detector: {e}")


async def _log_chat_detector(event_message) -> None:
    """异步监听日志事件，识别玩家聊天"""
    try:
        level = event_message.get("level", "")
        source = event_message.get("source", "")
        message = event_message.get("message", "")

        if level != "INFO" or "minecraft" not in source.lower():
            return

        match = CHAT_PATTERN.search(message)
        if not match:
            return

        player_name = match.group(1).strip()
        chat_content = match.group(2).strip()
        timestamp = datetime.now().isoformat()
        server_time = event_message.get("time", "")

        from yasl.event_bus.core import bus
        await bus.player_chat_async(
            player_name=player_name,
            message=chat_content,
            timestamp=timestamp,
            server_time=server_time,
            source=source,
        )

    except Exception as e:
        logger.error(f"Error in _log_chat_detector: {e}")


def setup_default_subscribers(bus_instance=None):
    """
    设置默认订阅者
    
    Args:
        bus_instance: 事件总线实例，如果为None则使用全局实例
    """
    from yasl.event_bus.core import EventPriority, bus as default_bus
    
    bus_to_use = bus_instance or default_bus
    bus_to_use.subscribe("log", _log_lifecycle_detector, EventPriority.LOW)
    bus_to_use.subscribe("log", _log_chat_detector, EventPriority.LOW)