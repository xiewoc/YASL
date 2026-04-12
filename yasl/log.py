"""日志解析和处理模块"""
import sys
import platform
import os
import logging
from datetime import datetime
import re
from enum import Enum
from typing import Optional, Tuple, Dict, Any, List, Pattern, Union
from contextlib import contextmanager

# 延迟导入以避免循环导入问题
_HAS_EVENT_BUS = False
_publish_async_func = None

try:
    # 使用字符串导入避免循环导入
    import importlib
    
    # 检查模块是否存在
    event_bus_spec = importlib.util.find_spec("yasl.event_bus")
    if event_bus_spec:
        # 动态导入 publish_async 函数
        event_bus_module = importlib.import_module("yasl.event_bus")
        _publish_async_func = getattr(event_bus_module, "publish_async", None)
        _HAS_EVENT_BUS = _publish_async_func is not None
except (ImportError, AttributeError):
    pass

logger = logging.getLogger(__name__)


class LogLevel(Enum):
    """日志级别枚举"""
    RAW = 0
    DEBUG = 1
    INFO = 2
    WARN = 3
    ERROR = 4
    FATAL = 5
    DONE = 6
    PLAYER = 7

    @classmethod
    def from_string(cls, level_str: str) -> "LogLevel":
        """从字符串转换为LogLevel"""
        level_str = level_str.upper()
        string_map = {
            "RAW": cls.RAW,
            "DEBUG": cls.DEBUG,
            "INFO": cls.INFO,
            "STARTED": cls.INFO,
            "PREPARING": cls.INFO,
            "SHUTTING_DOWN": cls.INFO,
            "STOPPING": cls.INFO,
            "WARN": cls.WARN,
            "WARNING": cls.WARN,
            "ERROR": cls.ERROR,
            "EXCEPTION": cls.ERROR,
            "FAIL": cls.ERROR,
            "SUCCESS": cls.ERROR,
            "FATAL": cls.FATAL,
            "CRITICAL": cls.FATAL,
            "CRASH": cls.FATAL,
            "DONE": cls.DONE,
            "PLAYER": cls.PLAYER,
        }
        return string_map.get(level_str, cls.RAW)

    @classmethod
    def from_message_type(cls, msg_type: str) -> "LogLevel":
        """从消息类型转换为LogLevel"""
        msg_type = msg_type.upper()
        msg_type_map = {
            "DONE": cls.DONE,
            "PLAYER": cls.PLAYER,
            "STARTED": cls.INFO,
            "PREPARING": cls.INFO,
            "STARTING": cls.INFO,
            "STOPPING": cls.INFO,
            "SUCCESS": cls.ERROR,
            "FAIL": cls.ERROR,
            "EXCEPTION": cls.ERROR,
            "ERROR": cls.ERROR,
            "CRASH": cls.FATAL,
        }
        return msg_type_map.get(msg_type, cls.INFO)


class LogEntry:
    """日志条目数据类"""
    
    __slots__ = [
        "time",
        "thread",
        "source",
        "message",
        "level",
        "extra_info",
        "raw_line",
    ]
    
    def __init__(
        self,
        time: str,
        thread: str,
        source: str,
        message: str,
        level: LogLevel,
        extra_info: Dict[str, Any],
        raw_line: str = "",
    ):
        self.time = time
        self.thread = thread
        self.source = source
        self.message = message
        self.level = level
        self.extra_info = extra_info
        self.raw_line = raw_line
    
    def __repr__(self):
        return (
            f"LogEntry(time={self.time!r}, thread={self.thread!r}, "
            f"source={self.source!r}, level={self.level}, "
            f"message={self.message[:50]!r}...)"
        )
    
    def as_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "time": self.time,
            "thread": self.thread,
            "source": self.source,
            "message": self.message,
            "level": self.level.name,
            "extra_info": self.extra_info,
            "raw_line": self.raw_line,
        }
    
    def as_tuple(self) -> Tuple[str, str, str, str, LogLevel, Dict[str, Any]]:
        """转换为元组格式以保持向后兼容性"""
        return (
            self.time,
            self.thread,
            self.source,
            self.message,
            self.level,
            self.extra_info,
        )


class ColorScheme:
    """颜色方案配置"""
    
    def __init__(self, color_mode: str = "auto"):
        """
        初始化颜色方案
        
        Args:
            color_mode: 颜色模式，可选值:
                - "auto": 自动检测（默认）
                - "truecolor": 强制使用 24 位真彩色
                - "16": 强制使用 16 色
                - "none": 不使用颜色
        """
        self.color_mode = self._detect_color_mode(color_mode)
        
        if self.color_mode == "none":
            # 无颜色模式
            self._init_no_colors()
        elif self.color_mode == "16":
            # 16 色模式
            self._init_16_colors()
        else:
            # 24 位真彩色模式（默认）
            self._init_truecolor()
    
    def _detect_color_mode(self, color_mode: str) -> str:
        """自动检测终端颜色支持"""
        if color_mode != "auto":
            return color_mode
        
        # 检查环境变量
        if "NO_COLOR" in os.environ:
            return "none"
        
        # 检查终端类型
        if platform.system().lower() == "windows":
            # Windows: 检查是否启用 VT 模式
            if self._supports_windows_vt():
                return "truecolor"  # Windows Terminal 支持 truecolor
            else:
                return "16"  # Windows cmd 不支持真彩色
        
        # Unix-like 系统
        term = os.environ.get("TERM", "")
        if "truecolor" in term or "24bit" in term:
            return "truecolor"
        elif "256" in term:
            return "truecolor"  # 256色终端也使用真彩色格式（兼容）
        
        # 检查是否在交互式终端中
        if hasattr(sys.stdout, "isatty") and sys.stdout.isatty():
            return "truecolor"
        
        return "16"
    
    def _supports_windows_vt(self) -> bool:
        """检查 Windows 是否支持 VT 颜色"""
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            STD_OUTPUT_HANDLE = -11
            
            hOut = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
            mode = ctypes.c_uint32()
            
            if kernel32.GetConsoleMode(hOut, ctypes.byref(mode)):
                return bool(mode.value & ENABLE_VIRTUAL_TERMINAL_PROCESSING)
        except Exception:
            pass
        return False
    
    def _init_no_colors(self):
        """初始化无颜色模式"""
        self.raw = ""
        self.debug = ""
        self.info = ""
        self.warn = ""
        self.error = ""
        self.fatal = ""
        self.done = ""
        self.player = ""
        
        self.done_tag = ""
        self.success_tag = ""
        self.command_tag = ""
        self.source_tag = ""
        self.mc_server_tag = ""
        self.player_tag = ""
        self.timer_tag = ""
        self.player_highlight = ""
        
        self.reset = ""
    
    def _init_16_colors(self):
        """初始化 16 色模式"""
        # 标准 ANSI 16 色
        self.raw = "\033[90m"      # 亮黑
        self.debug = "\033[36m"     # 青色
        self.info = "\033[37m"     # 白色
        self.warn = "\033[33m"     # 黄色
        self.error = "\033[31m"    # 红色
        self.fatal = "\033[35m"    # 洋红
        self.done = "\033[32m"     # 绿色
        self.player = "\033[36m"   # 青色
        
        self.done_tag = "\033[32m"
        self.success_tag = "\033[32m"
        self.command_tag = "\033[96m"
        self.source_tag = "\033[92m"
        self.mc_server_tag = "\033[33m"
        self.player_tag = "\033[36m"
        self.timer_tag = "\033[94m"
        self.player_highlight = "\033[36m"
        
        self.reset = "\033[0m"
    
    def _init_truecolor(self):
        """初始化 24 位真彩色模式"""
        # 24 位真彩色
        self.raw = "\033[38;2;128;128;128m"       # 灰色
        self.debug = "\033[38;2;0;255;255m"       # 青色
        self.info = "\033[38;2;255;255;255m"      # 白色
        self.warn = "\033[38;2;255;255;0m"        # 黄色
        self.error = "\033[38;2;255;0;0m"         # 红色
        self.fatal = "\033[38;2;255;0;255m"      # 洋红
        self.done = "\033[38;2;255;201;250m"     # 粉色
        self.player = "\033[38;2;0;255;255m"      # 青色
        
        self.done_tag = "\033[38;2;255;201;250m"
        self.success_tag = "\033[38;2;0;128;0m"
        self.command_tag = "\033[38;2;255;207;125m"
        self.source_tag = "\033[38;2;255;207;155m"
        self.mc_server_tag = "\033[38;2;227;215;189m"
        self.player_tag = "\033[38;2;187;239;255m"
        self.timer_tag = "\033[38;2;150;200;255m"
        self.player_highlight = "\033[38;2;187;239;255m"
        
        self.reset = "\033[0m"
    
    def get_level_color(self, level: LogLevel) -> str:
        """获取日志级别对应的颜色"""
        color_map = {
            LogLevel.RAW: self.raw,
            LogLevel.DEBUG: self.debug,
            LogLevel.INFO: self.info,
            LogLevel.WARN: self.warn,
            LogLevel.ERROR: self.error,
            LogLevel.FATAL: self.fatal,
            LogLevel.DONE: self.done,
            LogLevel.PLAYER: self.player,
        }
        return color_map.get(level, self.info)


class SpecialPattern:
    """特殊模式匹配器，使用缓存提高性能"""
    
    # 预编译的正则表达式 - 按匹配频率排序（高频在前）
    PATTERNS = {
        # 高频模式
        "player_chat": re.compile(r"^<(\w{1,16})>\s+(.+)$"),
        "player_join": re.compile(r"^(\w{1,16})\s+joined the game$", re.IGNORECASE),
        "player_leave_left": re.compile(r"^(\w{1,16})\s+left the game$", re.IGNORECASE),
        "player_leave_lost": re.compile(r"^(\w{1,16})\s+lost connection:\s*(.*)$", re.IGNORECASE),
        # 中频模式
        "done": re.compile(r"^Done\s*\((\d+\.\d+s)\)!.*$", re.IGNORECASE),
        "preparing": re.compile(r"^Preparing spawn area:\s*(\d+)%.*$", re.IGNORECASE),
        "starting": re.compile(r"^Starting Minecraft server on .*$", re.IGNORECASE),
        "stopping": re.compile(r"^Stopping server.*$", re.IGNORECASE),
        # 低频模式
        "started": re.compile(r"^.*server.*started.*$", re.IGNORECASE),
        "success": re.compile(r"^.*success.*$", re.IGNORECASE),
        "fail": re.compile(r"^.*fail.*$", re.IGNORECASE),
        "exception": re.compile(r"^.*exception.*$", re.IGNORECASE),
        "error": re.compile(r"^.*error.*$", re.IGNORECASE),
        "crash": re.compile(r"^.*crash.*$", re.IGNORECASE),
        "shutting_down": re.compile(r"^.*shutting down.*$", re.IGNORECASE),
        "player_say": re.compile(r"^\[Server:\s*([^\]]+)\]\s*(.+)$", re.IGNORECASE),
        "player_whisper": re.compile(
            r"^\[(\w{1,16})\s*->\s*(\w{1,16})\]\s+(.+)$",
            re.IGNORECASE,
        ),
        "player_command": re.compile(
            r"^(\w{1,16})\s+(?:issued server command|executed):?\s+(/.+)$",
            re.IGNORECASE,
        ),
        "cant_keep_up": re.compile(
            r"Can't keep up! Is the server overloaded\? Running\s*(\d+)ms or\s*(\d+) ticks behind",
            re.IGNORECASE,
        ),
    }
    
    TYPE_TO_LEVEL = {
        "normal": LogLevel.INFO,
        "starting": LogLevel.INFO,
        "stopping": LogLevel.INFO,
        "started": LogLevel.INFO,
        "done": LogLevel.DONE,
        "preparing": LogLevel.INFO,
        "success": LogLevel.ERROR,
        "fail": LogLevel.ERROR,
        "exception": LogLevel.ERROR,
        "error": LogLevel.ERROR,
        "crash": LogLevel.FATAL,
        "shutting_down": LogLevel.INFO,
        "player_join": LogLevel.PLAYER,
        "player_leave": LogLevel.PLAYER,
        "player_chat": LogLevel.PLAYER,
        "player_whisper": LogLevel.PLAYER,
        "player_say": LogLevel.INFO,
        "player_command": LogLevel.INFO,
        "cant_keep_up": LogLevel.WARN,
    }
    
    # 缓存匹配结果
    _cache: Dict[str, Tuple[str, Dict[str, Any]]] = {}
    _cache_max_size = 1000
    
    def match(self, message: str) -> Tuple[str, Dict[str, Any]]:
        """匹配特殊模式，使用缓存提高性能"""
        # 检查缓存
        if message in self._cache:
            return self._cache[message]
        
        extra_info = {"type": "normal"}
        
        for msg_type, pattern in self.PATTERNS.items():
            match = pattern.search(message)
            if match:
                extra_info["type"] = msg_type
                self._extract_match_info(msg_type, match, extra_info)
                break
        
        # 缓存结果
        if len(self._cache) >= self._cache_max_size:
            self._cache.clear()
        self._cache[message] = (extra_info["type"], extra_info.copy())
        
        return extra_info["type"], extra_info
    
    def _extract_match_info(self, msg_type: str, match: re.Match, extra_info: Dict[str, Any]):
        """提取匹配信息"""
        extractors = {
            "done": lambda: {"time_taken": match.group(1)},
            "preparing": lambda: {"percentage": match.group(1)},
            "player_join": lambda: {
                "player_name": match.group(1).strip(),
                "action": "join",
            },
            # player_leave_lost: "玩家名 lost connection: 原因"
            "player_leave_lost": lambda: {
                "player_name": match.group(1).strip(),
                "reason": match.group(2).strip() if match.lastindex and match.lastindex >= 2 else "",
                "action": "leave",
            },
            # player_leave_left: "玩家名 left the game"
            "player_leave_left": lambda: {
                "player_name": match.group(1).strip(),
                "reason": "",
                "action": "leave",
            },
            # 兼容旧的 player_leave
            "player_leave": lambda: {
                "player_name": match.group(1).strip(),
                "reason": match.group(2).strip() if match.lastindex and match.lastindex >= 2 else "",
                "action": "leave",
            },
            "player_chat": lambda: {
                "player_name": match.group(1).strip(),
                "message": match.group(2).strip(),
                "action": "chat",
            },
            "player_whisper": lambda: {
                "sender": match.group(1).strip(),
                "receiver": match.group(2).strip(),
                "message": match.group(3).strip(),
                "action": "whisper",
            },
            "player_say": lambda: {
                "player_name": match.group(1).strip(),
                "message": match.group(2).strip(),
                "action": "say",
            },
            "player_command": lambda: {
                "player_name": match.group(1).strip(),
                "command": match.group(2).strip(),
                "action": "command",
            },
            "cant_keep_up": lambda: {
                "ms": int(match.group(1)) if match.lastindex and match.lastindex >= 1 else 0,
                "ticks": int(match.group(2)) if match.lastindex and match.lastindex >= 2 else 0,
            },
        }
        
        # 处理 player_leave 的两种情况
        if msg_type in ("player_leave_lost", "player_leave_left"):
            msg_type = "player_leave"
        
        if extractor := extractors.get(msg_type):
            extra_info.update(extractor())


class ColorSupport:
    """颜色支持检测"""
    
    _supports_colors_cached: Optional[bool] = None
    
    @classmethod
    def supports_colors(cls) -> bool:
        """检测是否支持颜色输出"""
        if cls._supports_colors_cached is not None:
            return cls._supports_colors_cached
        
        if "NO_COLOR" in os.environ:
            cls._supports_colors_cached = False
            return False
        
        if "FORCE_COLOR" in os.environ:
            cls._supports_colors_cached = True
            return True
        
        if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
            cls._supports_colors_cached = False
            return False
        
        if platform.system().lower() == "windows":
            cls._supports_colors_cached = cls._enable_windows_vt()
            return cls._supports_colors_cached
        
        cls._supports_colors_cached = True
        return True
    
    @staticmethod
    def _enable_windows_vt() -> bool:
        """启用Windows虚拟终端"""
        try:
            import ctypes
            
            kernel32 = ctypes.windll.kernel32
            ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            STD_OUTPUT_HANDLE = -11
            
            hOut = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
            mode = ctypes.c_uint32()
            
            if kernel32.GetConsoleMode(hOut, ctypes.byref(mode)):
                mode.value |= ENABLE_VIRTUAL_TERMINAL_PROCESSING
                kernel32.SetConsoleMode(hOut, mode)
                return True
        except Exception:
            pass
        return False


class EventPublisher:
    """事件发布器"""
    
    @staticmethod
    async def publish_events_async(
        time: str,
        thread: str,
        source: str,
        message: str,
        level: LogLevel,
        extra_info: Dict[str, Any],
        should_publish: bool = True
    ) -> bool:
        """异步发布事件"""
        if not _HAS_EVENT_BUS or not should_publish or not _publish_async_func:
            return False
        
        try:
            await _publish_async_func(
                "log",
                time=time,
                thread=thread,
                source=source,
                message=message,
                level=level.name,
                extra=extra_info,
            )
            return True
        except Exception as e:
            logger.debug(f"Failed to publish log event: {e}")
            return False


class LogFilter:
    """日志过滤器"""
    
    # 预编译日志模式正则 - 支持标准格式和中文农历格式
    # 标准: [HH:MM:SS.SSS] [thread/LEVEL] [source]: message
    # 中文: [D月YYYY HH:MM:SS.SSS] [thread/LEVEL] [source]: message
    LOG_PATTERN: Pattern = re.compile(
        r"(?:\[(?P<time>[^\]]+)\]\s*)?"
        r"\[(?P<thread>[^\/]+)\/(?P<level>[A-Za-z]+)\]\s*"
        r"(?:\[(?P<source>[^\]]+)\]\s*:?\s*)?"
        r"(?P<message>.*)"
    )
    
    # 缓存解析结果
    _parse_cache: Dict[str, Optional[Tuple[str, str, str, str, LogLevel, Dict[str, Any]]]] = {}
    _cache_max_size = 2000
    
    def __init__(
        self,
        min_level: LogLevel = LogLevel.INFO,
        use_colors: Optional[bool] = None,
        filter_sources: Optional[List[str]] = None,
        enable_event_publishing: bool = True,
        cache_size: int = 2000,
    ):
        """
        初始化日志过滤器
        
        Args:
            min_level: 最低日志级别
            use_colors: 是否使用颜色（None表示自动检测）
            filter_sources: 要过滤的源列表
            enable_event_publishing: 是否启用事件发布
            cache_size: 解析缓存大小
        """
        self.min_level = min_level
        self.enable_event_publishing = enable_event_publishing and _HAS_EVENT_BUS
        
        # 颜色支持
        if use_colors is None:
            self.use_colors = ColorSupport.supports_colors()
        else:
            self.use_colors = use_colors
        
        # 源过滤器
        self.filter_sources = (
            {fs.lower() for fs in filter_sources} if filter_sources else set()
        )
        
        # 颜色方案
        self.color_scheme = ColorScheme() if self.use_colors else None
        
        # 模式匹配器
        self.pattern_matcher = SpecialPattern()
        
        # 缓存配置
        self._cache_max_size = cache_size
        
        # 向后兼容，保留 self.colors 属性
        if self.use_colors and self.color_scheme:
            self.colors = {
                LogLevel.RAW: self.color_scheme.raw,
                LogLevel.DEBUG: self.color_scheme.debug,
                LogLevel.INFO: self.color_scheme.info,
                LogLevel.WARN: self.color_scheme.warn,
                LogLevel.ERROR: self.color_scheme.error,
                LogLevel.FATAL: self.color_scheme.fatal,
                LogLevel.DONE: self.color_scheme.done,
                LogLevel.PLAYER: self.color_scheme.player,
                "DONE_TAG": self.color_scheme.done_tag,
                "SUCCESS_TAG": self.color_scheme.success_tag,
                "COMMAND_TAG": self.color_scheme.command_tag,
                "SOURCE_TAG": self.color_scheme.source_tag,
                "MC_SERVER_TAG": self.color_scheme.mc_server_tag,
                "PLAYER_TAG": self.color_scheme.player_tag,
                "TIMER_TAG": self.color_scheme.timer_tag,
                "RESET": self.color_scheme.reset,
                "PLAYER_HIGHLIGHT": self.color_scheme.player_highlight,
            }
        else:
            self.colors = {}
    
    def _get_cached_parse(self, line: str) -> Optional[Tuple[str, str, str, str, LogLevel, Dict[str, Any]]]:
        """获取缓存的解析结果"""
        if line in self._parse_cache:
            return self._parse_cache[line]
        return None
    
    def _set_cached_parse(self, line: str, result: Optional[Tuple]):
        """设置解析结果到缓存"""
        if len(self._parse_cache) >= self._cache_max_size:
            # 简单的LRU策略：清除一半缓存
            keys = list(self._parse_cache.keys())[:self._cache_max_size // 2]
            for key in keys:
                del self._parse_cache[key]
        
        self._parse_cache[line] = result
    
    async def parse_log_line_async(self, line: str) -> Optional[LogEntry]:
        """异步解析日志行，返回LogEntry对象"""
        # 检查缓存
        cached = self._get_cached_parse(line)
        if cached is not None:
            time, thread, source, message, final_level, extra_info = cached
            return LogEntry(
                time=time,
                thread=thread,
                source=source,
                message=message,
                level=final_level,
                extra_info=extra_info,
                raw_line=line,
            )
        
        match = self.LOG_PATTERN.search(line)
        if not match:
            self._set_cached_parse(line, None)
            return None
        
        # 提取基础信息
        time = match.group("time") or ""
        thread = match.group("thread")
        level_str = match.group("level")
        source = match.group("source") or thread
        message = match.group("message")
        
        # 确定日志级别
        parsed_level = LogLevel.from_string(level_str)
        msg_type, extra_info = self.pattern_matcher.match(message)
        final_level = self.pattern_matcher.TYPE_TO_LEVEL.get(msg_type, parsed_level)
        
        # 检查是否是Minecraft服务器核心日志
        if source and source.lower().startswith("minecraft/minecraftserver"):
            extra_info["force_highlight"] = True
        
        # 检查是否需要发布事件
        should_publish = (
            self.enable_event_publishing and 
            self._should_display_level(final_level) and
            not self._is_source_filtered(source)
        )
        
        # 异步发布基础日志事件
        if should_publish:
            await EventPublisher.publish_events_async(
                time, thread, source, message, final_level, extra_info, should_publish
            )
        
        # 缓存结果
        result = (time, thread, source, message, final_level, extra_info)
        self._set_cached_parse(line, result)
        
        return LogEntry(
            time=time,
            thread=thread,
            source=source,
            message=message,
            level=final_level,
            extra_info=extra_info,
            raw_line=line,
        )
    
    def parse_log_line_tuple(
        self, line: str
    ) -> Optional[Tuple[str, str, str, str, LogLevel, Dict[str, Any]]]:
        """同步解析日志行（向后兼容）"""
        # 检查缓存
        cached = self._get_cached_parse(line)
        if cached is not None:
            return cached
        
        match = self.LOG_PATTERN.search(line)
        if not match:
            self._set_cached_parse(line, None)
            return None
        
        # 提取基础信息
        time = match.group("time") or ""
        thread = match.group("thread")
        level_str = match.group("level")
        source = match.group("source") or thread
        message = match.group("message")
        
        # 确定日志级别
        parsed_level = LogLevel.from_string(level_str)
        msg_type, extra_info = self.pattern_matcher.match(message)
        final_level = self.pattern_matcher.TYPE_TO_LEVEL.get(msg_type, parsed_level)
        
        # 检查是否是Minecraft服务器核心日志
        if source and source.lower().startswith("minecraft/minecraftserver"):
            extra_info["force_highlight"] = True
        
        result = (time, thread, source, message, final_level, extra_info)
        self._set_cached_parse(line, result)
        
        return result
    
    def _should_display_level(self, level: LogLevel) -> bool:
        """检查是否应该显示该级别日志"""
        return level.value >= self.min_level.value
    
    def should_show(self, entry: LogEntry) -> bool:
        """判断是否应该显示日志"""
        # 始终显示Minecraft服务器核心日志
        if entry.source and entry.source.lower().startswith("minecraft/minecraftserver"):
            return True
        
        # 检查源过滤器
        if self._is_source_filtered(entry.source):
            return False
        
        # 检查级别过滤器
        return self._should_display_level(entry.level)
    
    def should_show_log(self, level: LogLevel, source: Optional[str]) -> bool:
        """向后兼容的方法"""
        try:
            if source and source.lower().startswith("minecraft/minecraftserver"):
                return True
        except Exception:
            pass
        
        if self._is_source_filtered(source or ""):
            return False
        return self._should_display_level(level)
    
    def _is_source_filtered(self, source: str) -> bool:
        """检查源是否被过滤"""
        if not source or not self.filter_sources:
            return False
        base = source.split("/", 1)[0].lower()
        return base in self.filter_sources
    
    def format_log(
        self,
        time: str,
        thread: str,
        source: str,
        message: str,
        level: LogLevel,
        extra_info: Dict[str, Any],
    ) -> str:
        """格式化日志输出（向后兼容）"""
        entry = LogEntry(time, thread, source, message, level, extra_info)
        return self._format_log_entry(entry)
    
    def _format_log_entry(self, entry: LogEntry) -> str:
        """格式化LogEntry对象"""
        if not self.use_colors:
            return self._format_plain(entry)
        return self._format_colored(entry)
    
    def _format_plain(self, entry: LogEntry) -> str:
        """无颜色格式化"""
        display_tag = self._get_display_tag(entry.extra_info, entry.level)
        time_part = f"[{entry.time}] " if entry.time else ""
        return f"{time_part}{display_tag} [{entry.source}]: {entry.message}"
    
    def _format_colored(self, entry: LogEntry) -> str:
        """带颜色格式化"""
        if not self.color_scheme:
            return self._format_plain(entry)
        
        colors = self.color_scheme
        
        # 获取显示标签和颜色
        display_tag = self._get_display_tag(entry.extra_info, entry.level)
        tag_color = self._get_tag_color(entry.extra_info, entry.level)
        reset_color = colors.reset
        
        # 格式化消息（高亮特殊内容）
        formatted_message = self._format_message_content(entry.message, entry.extra_info)
        
        # 获取源标签颜色
        source_color = colors.source_tag
        if entry.extra_info.get("force_highlight"):
            source_color = colors.mc_server_tag
        
        # 组合输出
        time_part = f"[{entry.time}] " if entry.time else ""
        colored_tag = f"{tag_color}{display_tag}{reset_color}"
        colored_source = f"{source_color}[{entry.source}]{reset_color}"
        
        return f"{time_part}{colored_tag} {colored_source}: {formatted_message}"
    
    def _get_display_tag(self, extra_info: Dict[str, Any], level: LogLevel) -> str:
        """获取显示标签"""
        msg_type = extra_info.get("type", "normal")
        
        if msg_type == "normal":
            return f"[{level.name}]"
        
        if msg_type in ["player_join", "player_leave"]:
            action = "JOIN" if msg_type == "player_join" else "LEAVE"
            return f"[PLAYER_{action}]"
        
        return f"[{msg_type.upper()}]"
    
    def _get_tag_color(self, extra_info: Dict[str, Any], level: LogLevel) -> str:
        """获取标签颜色"""
        if not self.color_scheme:
            return ""
        
        colors = self.color_scheme
        
        msg_type = extra_info.get("type", "normal")
        color_map = {
            "normal": colors.get_level_color(level),
            "done": colors.done_tag,
            "success": colors.success_tag,
            "player_join": colors.player_tag,
            "player_leave": colors.player_tag,
        }
        
        return color_map.get(msg_type, colors.get_level_color(level))
    
    def _format_message_content(self, message: str, extra_info: Dict[str, Any]) -> str:
        """格式化消息内容（高亮特殊部分）"""
        if not self.use_colors or not self.color_scheme:
            return message
        
        colors = self.color_scheme
        msg_type = extra_info.get("type", "normal")
        
        # Done消息高亮
        if msg_type == "done":
            done_match = SpecialPattern.PATTERNS["done"].search(message)
            if done_match:
                done_color = colors.done_tag
                reset_color = colors.reset
                start = done_match.start()
                original_done = message[start : start + 4]
                return message.replace(original_done, f"{done_color}Done{reset_color}", 1)
        
        # 玩家消息高亮
        elif msg_type in ["player_join", "player_leave"]:
            player_name = extra_info.get("player_name")
            if player_name:
                player_color = colors.player_highlight
                reset_color = colors.reset
                player_pattern = re.compile(r"\b" + re.escape(player_name) + r"\b")
                return player_pattern.sub(f"{player_color}{player_name}{reset_color}", message)
        
        return message
    
    def format_raw_log(self, line: str) -> str:
        """格式化原始日志行"""
        current_time = datetime.now().strftime("%H:%M:%S")
        
        # 尝试特殊模式匹配
        msg_type, extra_info = self.pattern_matcher.match(line)
        if msg_type != "normal":
            level = self.pattern_matcher.TYPE_TO_LEVEL.get(msg_type, LogLevel.RAW)
            if self._should_display_level(level):
                return self._format_raw_special(line, current_time, msg_type, level, extra_info)
        
        # 普通原始日志
        if self._should_display_level(LogLevel.RAW):
            return f"[{current_time}]: {line}"
        
        return ""
    
    def _format_raw_special(
        self,
        line: str,
        current_time: str,
        msg_type: str,
        level: LogLevel,
        extra_info: Dict[str, Any],
    ) -> str:
        """格式化特殊原始日志"""
        if not self.use_colors:
            return f"[{current_time}] [{msg_type.upper()}]: {line}"
        
        if not self.color_scheme:
            return f"[{current_time}] [{msg_type.upper()}]: {line}"
        
        colors = self.color_scheme
        tag_color = self._get_tag_color(extra_info, level)
        reset_color = colors.reset
        
        formatted_line = self._format_message_content(line, extra_info)
        return f"[{current_time}] {tag_color}[{msg_type.upper()}]{reset_color}: {formatted_line}"
    
    def clear_cache(self) -> None:
        """清除解析缓存"""
        self._parse_cache.clear()
        self.pattern_matcher._cache.clear()


# 全局默认过滤器实例
_default_filter: Optional[LogFilter] = None


def get_default_filter(
    min_level: LogLevel = LogLevel.INFO,
    use_colors: Optional[bool] = None,
    filter_sources: Optional[List[str]] = None,
    enable_event_publishing: bool = True,
) -> LogFilter:
    """获取或创建全局默认过滤器"""
    global _default_filter
    
    if _default_filter is None:
        _default_filter = LogFilter(
            min_level=min_level,
            use_colors=use_colors,
            filter_sources=filter_sources,
            enable_event_publishing=enable_event_publishing,
        )
    else:
        # 更新现有过滤器的配置
        if min_level != _default_filter.min_level:
            _default_filter.min_level = min_level
        if use_colors is not None and use_colors != _default_filter.use_colors:
            _default_filter.use_colors = use_colors
            _default_filter.color_scheme = ColorScheme() if use_colors else None
        if filter_sources is not None:
            _default_filter.filter_sources = {fs.lower() for fs in filter_sources}
    
    return _default_filter


def set_default_filter(filter_instance: LogFilter) -> None:
    """设置全局默认过滤器"""
    global _default_filter
    _default_filter = filter_instance


# 向后兼容的函数
def parse_log_line(
    line: str,
    min_level: LogLevel = LogLevel.INFO,
    use_colors: Optional[bool] = None,
    filter_sources: Optional[List[str]] = None,
) -> Optional[str]:
    """解析并格式化日志行（向后兼容）"""
    filter_instance = get_default_filter(min_level, use_colors, filter_sources)
    
    result = filter_instance.parse_log_line_tuple(line)
    if not result:
        return None
    
    time, thread, source, message, level, extra_info = result
    
    if not filter_instance.should_show_log(level, source):
        return None
    
    return filter_instance.format_log(time, thread, source, message, level, extra_info)


async def parse_log_line_async(
    line: str,
    min_level: LogLevel = LogLevel.INFO,
    use_colors: Optional[bool] = None,
    filter_sources: Optional[List[str]] = None,
) -> Optional[str]:
    """异步解析并格式化日志行"""
    filter_instance = get_default_filter(min_level, use_colors, filter_sources)
    
    entry = await filter_instance.parse_log_line_async(line)
    if not entry:
        return None
    
    if not filter_instance.should_show(entry):
        return None
    
    return filter_instance._format_log_entry(entry)


@contextmanager
def temporary_filter_config(
    min_level: Optional[LogLevel] = None,
    use_colors: Optional[bool] = None,
    filter_sources: Optional[List[str]] = None,
    enable_event_publishing: Optional[bool] = None,
):
    """
    临时修改过滤器配置的上下文管理器
    
    Example:
        with temporary_filter_config(min_level=LogLevel.DEBUG):
            result = parse_log_line(line)
    """
    global _default_filter
    
    if _default_filter is None:
        _default_filter = get_default_filter()
    
    # 保存原始配置
    original_config = {
        "min_level": _default_filter.min_level,
        "use_colors": _default_filter.use_colors,
        "filter_sources": _default_filter.filter_sources.copy() if _default_filter.filter_sources else set(),
        "enable_event_publishing": _default_filter.enable_event_publishing,
    }
    
    try:
        # 应用临时配置
        if min_level is not None:
            _default_filter.min_level = min_level
        if use_colors is not None:
            _default_filter.use_colors = use_colors
            _default_filter.color_scheme = ColorScheme() if use_colors else None
        if filter_sources is not None:
            _default_filter.filter_sources = {fs.lower() for fs in filter_sources}
        if enable_event_publishing is not None:
            _default_filter.enable_event_publishing = enable_event_publishing
        
        yield _default_filter
    finally:
        # 恢复原始配置
        _default_filter.min_level = original_config["min_level"]
        _default_filter.use_colors = original_config["use_colors"]
        _default_filter.filter_sources = original_config["filter_sources"]
        _default_filter.enable_event_publishing = original_config["enable_event_publishing"]
        
        # 重新创建颜色方案如果需要
        if _default_filter.use_colors and not _default_filter.color_scheme:
            _default_filter.color_scheme = ColorScheme()
        elif not _default_filter.use_colors:
            _default_filter.color_scheme = None