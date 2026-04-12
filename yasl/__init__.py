"""
YASL - Yet Another Server Launcher

Minecraft 服务器启动器核心包
"""

# 版本信息
__version__ = "2.0.0"
__author__ = "YASL Team"

# 导入核心模块
from yasl.utils import (
    get_timestamp,
    get_iso_timestamp,
    format_duration,
    Colors,
    supports_color,
    log_print,
    ensure_dir,
    get_project_root,
    PLAYER_PATTERNS,
    SERVER_PATTERNS,
    LOG_PATTERN,
)

from yasl.log import (
    LogLevel,
    LogFilter,
    LogEntry,
    ColorScheme,
    ColorSupport,
    SpecialPattern,
    parse_log_line,
    parse_log_line_async,
    get_default_filter,
    set_default_filter,
)

from yasl.main import (
    MinecraftServer,
    get_current_server,
)

from yasl.playtime import (
    PlayTimeManager,
    get_playtime_manager,
    create_playtime_manager,
)

from yasl.api import (
    set_server,
    get_server,
    get_playtime_manager as api_get_playtime_manager,
    start_api,
    stop_api,
)

# 事件总线
from yasl.event_bus import (
    EventBus,
    EventMessage,
    EventPriority,
    subscribe,
    on,
    publish_async,
    publish,
    emit_async,
    emit,
    bus,
)

# 扩展管理
from yasl.extension_manager import (
    ExtensionManager,
    get_extension_manager,
    reset_extension_manager,
    event_handler,
)

# 公共接口
__all__ = [
    # 版本
    "__version__",
    "__author__",
    # 工具函数
    "get_timestamp",
    "get_iso_timestamp",
    "format_duration",
    "Colors",
    "supports_color",
    "log_print",
    "ensure_dir",
    "get_project_root",
    # 正则表达式
    "PLAYER_PATTERNS",
    "SERVER_PATTERNS",
    "LOG_PATTERN",
    # 日志
    "LogLevel",
    "LogFilter",
    "LogEntry",
    "ColorScheme",
    "ColorSupport",
    "SpecialPattern",
    "parse_log_line",
    "parse_log_line_async",
    "get_default_filter",
    "set_default_filter",
    # 服务器
    "MinecraftServer",
    "get_current_server",
    # 游戏时间
    "PlayTimeManager",
    "get_playtime_manager",
    "create_playtime_manager",
    # API
    "set_server",
    "get_server",
    "api_get_playtime_manager",
    "start_api",
    "stop_api",
    # 事件总线
    "EventBus",
    "EventMessage",
    "EventPriority",
    "subscribe",
    "on",
    "publish_async",
    "publish",
    "emit_async",
    "emit",
    "bus",
    # 扩展
    "ExtensionManager",
    "get_extension_manager",
    "reset_extension_manager",
    "event_handler",
]