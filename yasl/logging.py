"""日志解析和颜色替换模块（精简版）"""
import sys
import platform
import os
import re
from enum import Enum
from typing import Optional, Tuple, Dict, Any, List, Pattern
from contextlib import contextmanager
from datetime import datetime


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
        level_str = level_str.upper()
        string_map = {
            "RAW": cls.RAW, "DEBUG": cls.DEBUG, "INFO": cls.INFO,
            "STARTED": cls.INFO, "PREPARING": cls.INFO, "SHUTTING_DOWN": cls.INFO,
            "STOPPING": cls.INFO, "WARN": cls.WARN, "WARNING": cls.WARN,
            "ERROR": cls.ERROR, "EXCEPTION": cls.ERROR, "FAIL": cls.ERROR,
            "SUCCESS": cls.ERROR, "FATAL": cls.FATAL, "CRITICAL": cls.FATAL,
            "CRASH": cls.FATAL, "DONE": cls.DONE, "PLAYER": cls.PLAYER,
        }
        return string_map.get(level_str, cls.RAW)

    @classmethod
    def from_message_type(cls, msg_type: str) -> "LogLevel":
        msg_type = msg_type.upper()
        msg_type_map = {
            "DONE": cls.DONE, "PLAYER": cls.PLAYER, "STARTED": cls.INFO,
            "PREPARING": cls.INFO, "STARTING": cls.INFO, "STOPPING": cls.INFO,
            "SUCCESS": cls.ERROR, "FAIL": cls.ERROR, "EXCEPTION": cls.ERROR,
            "ERROR": cls.ERROR, "CRASH": cls.FATAL,
        }
        return msg_type_map.get(msg_type, cls.INFO)


class LogEntry:
    """日志条目数据类"""
    __slots__ = ["time", "thread", "source", "message", "level", "extra_info", "raw_line"]

    def __init__(self, time: str, thread: str, source: str, message: str,
                 level: LogLevel, extra_info: Dict[str, Any], raw_line: str = ""):
        self.time = time
        self.thread = thread
        self.source = source
        self.message = message
        self.level = level
        self.extra_info = extra_info
        self.raw_line = raw_line

    def __repr__(self):
        return (f"LogEntry(time={self.time!r}, thread={self.thread!r}, "
                f"source={self.source!r}, level={self.level}, "
                f"message={self.message[:50]!r}...)")

    def as_dict(self) -> Dict[str, Any]:
        return {
            "time": self.time, "thread": self.thread, "source": self.source,
            "message": self.message, "level": self.level.name,
            "extra_info": self.extra_info, "raw_line": self.raw_line,
        }


# ---------------------------------------------------------------------------
# 独立颜色配置 – 16 色（ANSI 3/4-bit）
# ---------------------------------------------------------------------------
COLORS_16 = {
    "raw":              "\033[90m",   # 亮黑（灰）        ←  灰 (128,128,128)
    "debug":            "\033[96m",   # 亮青              ←  青 (0,255,255)
    "info":             "\033[97m",   # 亮白              ←  白 (255,255,255)
    "warn":             "\033[93m",   # 亮黄              ←  黄 (255,255,0)
    "error":            "\033[91m",   # 亮红              ←  红 (255,0,0)
    "fatal":            "\033[95m",   # 亮品红            ←  品红 (255,0,255)
    "done":             "\033[95m",   # 亮品红（≈浅粉）   ←  浅粉 (255,201,250)
    "player":           "\033[96m",   # 亮青              ←  青 (0,255,255)
    "done_tag":         "\033[95m",   # 亮品红（≈浅粉）   ←  浅粉 (255,201,250)
    "success_tag":      "\033[32m",   # 绿                ←  深绿 (0,128,0)
    "command_tag":      "\033[93m",   # 亮黄（≈浅橙）     ←  浅橙 (255,207,125)
    "source_tag":       "\033[93m",   # 亮黄（≈米橙）     ←  米橙 (255,207,155)
    "mc_server_tag":    "\033[97m",   # 亮白（≈米灰）     ←  米灰 (227,215,189)
    "player_tag":       "\033[96m",   # 亮青（≈浅蓝）     ←  浅蓝 (187,239,255)
    "timer_tag":        "\033[94m",   # 亮蓝              ←  淡蓝 (150,200,255)
    "player_highlight": "\033[96m",   # 亮青（≈浅蓝）     ←  浅蓝 (187,239,255)
    "reset":            "\033[0m",
}

# ---------------------------------------------------------------------------
# 独立颜色配置 – 24-bit 真彩色
# ---------------------------------------------------------------------------
COLORS_TRUECOLOR = {
    "raw":              "\033[38;2;128;128;128m",   # 灰
    "debug":            "\033[38;2;0;255;255m",     # 青
    "info":             "\033[38;2;255;255;255m",   # 白
    "warn":             "\033[38;2;255;255;0m",     # 黄
    "error":            "\033[38;2;255;0;0m",       # 红
    "fatal":            "\033[38;2;255;0;255m",     # 品红
    "done":             "\033[38;2;255;201;250m",   # 浅粉
    "player":           "\033[38;2;0;255;255m",     # 青
    "done_tag":         "\033[38;2;255;201;250m",   # 浅粉
    "success_tag":      "\033[38;2;0;128;0m",       # 深绿
    "command_tag":      "\033[38;2;255;207;125m",   # 浅橙
    "source_tag":       "\033[38;2;255;207;155m",   # 米橙
    "mc_server_tag":    "\033[38;2;227;215;189m",   # 米灰
    "player_tag":       "\033[38;2;187;239;255m",   # 浅蓝
    "timer_tag":        "\033[38;2;150;200;255m",    # 淡蓝
    "player_highlight": "\033[38;2;187;239;255m",   # 浅蓝
    "reset":            "\033[0m",
}

# 颜色属性名列表（禁止外部修改顺序）
_COLOR_ATTRS = [
    "raw", "debug", "info", "warn", "error", "fatal",
    "done", "player",
    "done_tag", "success_tag", "command_tag", "source_tag",
    "mc_server_tag", "player_tag", "timer_tag", "player_highlight",
    "reset",
]


class ColorScheme:
    """颜色方案配置（支持自动检测、16色和真彩色，颜色定义已分立）"""

    __slots__ = (
        "color_mode",
        *_COLOR_ATTRS,
    )

    # 类型检查器需要显式声明以消除 setattr 带来的未知属性警告
    raw: str
    debug: str
    info: str
    warn: str
    error: str
    fatal: str
    done: str
    player: str
    done_tag: str
    success_tag: str
    command_tag: str
    source_tag: str
    mc_server_tag: str
    player_tag: str
    timer_tag: str
    player_highlight: str
    reset: str

    def __init__(self, color_mode: str = "auto"):
        self.color_mode = self._detect_color_mode(color_mode)
        if self.color_mode == "none":
            for attr in _COLOR_ATTRS:
                setattr(self, attr, "")
        elif self.color_mode == "16":
            for attr in _COLOR_ATTRS:
                setattr(self, attr, COLORS_16.get(attr, ""))
        else:
            for attr in _COLOR_ATTRS:
                setattr(self, attr, COLORS_TRUECOLOR.get(attr, ""))

    @staticmethod
    def _detect_color_mode(color_mode: str) -> str:
        if color_mode != "auto":
            return color_mode
        if "NO_COLOR" in os.environ:
            return "none"
        if platform.system().lower() == "windows":
            return "truecolor" if ColorScheme._supports_windows_vt() else "16"
        term = os.environ.get("TERM", "")
        if "truecolor" in term or "24bit" in term or "256" in term:
            return "truecolor"
        if hasattr(sys.stdout, "isatty") and sys.stdout.isatty():
            return "truecolor"
        return "16"

    @staticmethod
    def _supports_windows_vt() -> bool:
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

    def get_level_color(self, level: LogLevel) -> str:
        color_map = {
            LogLevel.RAW: self.raw, LogLevel.DEBUG: self.debug, LogLevel.INFO: self.info,
            LogLevel.WARN: self.warn, LogLevel.ERROR: self.error, LogLevel.FATAL: self.fatal,
            LogLevel.DONE: self.done, LogLevel.PLAYER: self.player,
        }
        return color_map.get(level, self.info)


class SpecialPattern:
    """特殊模式匹配（玩家进出、聊天、完成等）"""
    PATTERNS = {
        "player_chat": re.compile(r"^<(\w{1,16})>\s+(.+)$"),
        "player_join": re.compile(r"^(\w{1,16})\s+joined the game$", re.IGNORECASE),
        "player_leave_left": re.compile(r"^(\w{1,16})\s+left the game$", re.IGNORECASE),
        "player_leave_lost": re.compile(r"^(\w{1,16})\s+lost connection:\s*(.*)$", re.IGNORECASE),
        "done": re.compile(r"^Done\s*\((\d+\.\d+s)\)!.*$", re.IGNORECASE),
        "preparing": re.compile(r"^Preparing spawn area:\s*(\d+)%.*$", re.IGNORECASE),
        "starting": re.compile(r"^Starting Minecraft server on .*$", re.IGNORECASE),
        "stopping": re.compile(r"^Stopping server.*$", re.IGNORECASE),
        "started": re.compile(r"^.*server.*started.*$", re.IGNORECASE),
        "success": re.compile(r"^.*success.*$", re.IGNORECASE),
        "fail": re.compile(r"^.*fail.*$", re.IGNORECASE),
        "exception": re.compile(r"^.*exception.*$", re.IGNORECASE),
        "error": re.compile(r"^.*error.*$", re.IGNORECASE),
        "crash": re.compile(r"^.*crash.*$", re.IGNORECASE),
        "shutting_down": re.compile(r"^.*shutting down.*$", re.IGNORECASE),
        "player_say": re.compile(r"^\[Server:\s*([^\]]+)\]\s*(.+)$", re.IGNORECASE),
        "player_whisper": re.compile(r"^\[(\w{1,16})\s*->\s*(\w{1,16})\]\s+(.+)$", re.IGNORECASE),
        "player_command": re.compile(r"^(\w{1,16})\s+(?:issued server command|executed):?\s+(/.+)$", re.IGNORECASE),
        "cant_keep_up": re.compile(r"Can't keep up! Is the server overloaded\? Running\s*(\d+)ms or\s*(\d+) ticks behind", re.IGNORECASE),
    }
    TYPE_TO_LEVEL = {
        "normal": LogLevel.INFO, "starting": LogLevel.INFO, "stopping": LogLevel.INFO,
        "started": LogLevel.INFO, "done": LogLevel.DONE, "preparing": LogLevel.INFO,
        "success": LogLevel.ERROR, "fail": LogLevel.ERROR, "exception": LogLevel.ERROR,
        "error": LogLevel.ERROR, "crash": LogLevel.FATAL, "shutting_down": LogLevel.INFO,
        "player_join": LogLevel.PLAYER, "player_leave": LogLevel.PLAYER,
        "player_chat": LogLevel.PLAYER, "player_whisper": LogLevel.PLAYER,
        "player_say": LogLevel.INFO, "player_command": LogLevel.INFO,
        "cant_keep_up": LogLevel.WARN,
    }

    def match(self, message: str) -> Tuple[str, Dict[str, Any]]:
        extra_info = {"type": "normal"}
        for msg_type, pattern in self.PATTERNS.items():
            match = pattern.search(message)
            if match:
                extra_info["type"] = msg_type
                self._extract_match_info(msg_type, match, extra_info)
                break
        return extra_info["type"], extra_info

    def _extract_match_info(self, msg_type: str, match: re.Match, extra: Dict[str, Any]):
        if msg_type == "done":
            extra["time_taken"] = match.group(1)
        elif msg_type == "preparing":
            extra["percentage"] = match.group(1)
        elif msg_type == "player_join":
            extra.update({"player_name": match.group(1).strip(), "action": "join"})
        elif msg_type in ("player_leave_lost", "player_leave_left"):
            extra["player_name"] = match.group(1).strip()
            if msg_type == "player_leave_lost" and (match.lastindex or 0) >= 2:
                extra["reason"] = match.group(2).strip()
            else:
                extra["reason"] = ""
            extra["action"] = "leave"
        elif msg_type == "player_chat":
            extra.update({"player_name": match.group(1).strip(), "message": match.group(2).strip(), "action": "chat"})
        elif msg_type == "player_whisper":
            extra.update({"sender": match.group(1).strip(), "receiver": match.group(2).strip(),
                          "message": match.group(3).strip(), "action": "whisper"})
        elif msg_type == "player_say":
            extra.update({"player_name": match.group(1).strip(), "message": match.group(2).strip(), "action": "say"})
        elif msg_type == "player_command":
            extra.update({"player_name": match.group(1).strip(), "command": match.group(2).strip(), "action": "command"})
        elif msg_type == "cant_keep_up":
            extra.update({"ms": int(match.group(1)), "ticks": int(match.group(2))})


class ColorSupport:
    """颜色支持检测（终端能力）"""
    _supports_colors_cached: Optional[bool] = None

    @classmethod
    def supports_colors(cls) -> bool:
        if cls._supports_colors_cached is not None:
            return cls._supports_colors_cached
        if "NO_COLOR" in os.environ:
            cls._supports_colors_cached = False
        elif "FORCE_COLOR" in os.environ:
            cls._supports_colors_cached = True
        elif not (hasattr(sys.stdout, "isatty") and sys.stdout.isatty()):
            cls._supports_colors_cached = False
        elif platform.system().lower() == "windows":
            cls._supports_colors_cached = cls._enable_windows_vt()
        else:
            cls._supports_colors_cached = True
        return cls._supports_colors_cached

    @staticmethod
    def _enable_windows_vt() -> bool:
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


class LogFilter:
    """日志过滤器（解析、级别过滤、颜色格式化）"""
    LOG_PATTERN: Pattern = re.compile(
        r"(?:\[(?P<time>[^\]]+)\]\s*)?"
        r"\[(?P<thread>[^\/]+)\/(?P<level>[A-Za-z]+)\]\s*"
        r"(?:\[(?P<source>[^\]]+)\]\s*:?\s*)?"
        r"(?P<message>.*)"
    )

    def __init__(self, min_level: LogLevel = LogLevel.INFO, use_colors: Optional[bool] = None,
                 filter_sources: Optional[List[str]] = None):
        self.min_level = min_level
        self.use_colors = ColorSupport.supports_colors() if use_colors is None else use_colors
        self.filter_sources = {fs.lower() for fs in filter_sources} if filter_sources else set()
        self.color_scheme = ColorScheme() if self.use_colors else None
        self.pattern_matcher = SpecialPattern()

        # 向后兼容 colors 字典
        if self.use_colors and self.color_scheme:
            cs = self.color_scheme
            self.colors = {
                LogLevel.RAW: cs.raw, LogLevel.DEBUG: cs.debug, LogLevel.INFO: cs.info,
                LogLevel.WARN: cs.warn, LogLevel.ERROR: cs.error, LogLevel.FATAL: cs.fatal,
                LogLevel.DONE: cs.done, LogLevel.PLAYER: cs.player,
                "DONE_TAG": cs.done_tag, "SUCCESS_TAG": cs.success_tag,
                "COMMAND_TAG": cs.command_tag, "SOURCE_TAG": cs.source_tag,
                "MC_SERVER_TAG": cs.mc_server_tag, "PLAYER_TAG": cs.player_tag,
                "TIMER_TAG": cs.timer_tag, "RESET": cs.reset, "PLAYER_HIGHLIGHT": cs.player_highlight,
            }
        else:
            self.colors = {}

    def parse_log_line(self, line: str) -> Optional[LogEntry]:
        """解析日志行，返回 LogEntry 或 None"""
        match = self.LOG_PATTERN.search(line)
        if not match:
            return None

        time = match.group("time") or ""
        thread = match.group("thread")
        level_str = match.group("level")
        source = match.group("source") or thread
        message = match.group("message")

        parsed_level = LogLevel.from_string(level_str)
        msg_type, extra_info = self.pattern_matcher.match(message)
        final_level = self.pattern_matcher.TYPE_TO_LEVEL.get(msg_type, parsed_level)

        if source and source.lower().startswith("minecraft/minecraftserver"):
            extra_info["force_highlight"] = True

        # ---------- 触发器：通过事件总线发布事件 ----------
        self._fire_event(
            msg_type,
            time=time,
            thread=thread,
            source=source,
            message=message,
            level=final_level,
            line=line,
            **{k: v for k, v in extra_info.items() if k not in ("type", "force_highlight")},
        )

        return LogEntry(time, thread, source, message, final_level, extra_info, line)

    @staticmethod
    def _fire_event(msg_type: str, **kwargs: Any) -> None:
        """根据消息类型触发对应事件以及通用 log 事件。"""
        from yasl.event_bus import publish, TYPE_TO_EVENT  # pylance: ignore

        # 1. 通用 log 事件
        publish("log", **kwargs)

        # 2. 特定类型事件
        event_type = TYPE_TO_EVENT.get(msg_type)
        if event_type:
            publish(event_type, **kwargs)

    def should_show(self, entry: LogEntry) -> bool:
        if entry.source and entry.source.lower().startswith("minecraft/minecraftserver"):
            return True
        if self._is_source_filtered(entry.source):
            return False
        return entry.level.value >= self.min_level.value

    def _is_source_filtered(self, source: str) -> bool:
        if not source or not self.filter_sources:
            return False
        base = source.split("/", 1)[0].lower()
        return base in self.filter_sources

    def format_log(self, entry: LogEntry) -> str:
        """格式化日志（带颜色或无颜色）"""
        if not self.use_colors or not self.color_scheme:
            return self._format_plain(entry)
        return self._format_colored(entry)

    def _format_plain(self, entry: LogEntry) -> str:
        display_tag = self._get_display_tag(entry.extra_info, entry.level)
        time_part = f"[{entry.time}] " if entry.time else ""
        return f"{time_part}{display_tag} [{entry.source}]: {entry.message}"

    def _format_colored(self, entry: LogEntry) -> str:
        cs: ColorScheme = self.color_scheme  # type: ignore[assignment]
        display_tag = self._get_display_tag(entry.extra_info, entry.level)
        tag_color = self._get_tag_color(entry.extra_info, entry.level)
        reset = cs.reset

        formatted_message = self._format_message_content(entry.message, entry.extra_info)

        source_color = cs.source_tag
        if entry.extra_info.get("force_highlight"):
            source_color = cs.mc_server_tag

        time_part = f"[{entry.time}] " if entry.time else ""
        colored_tag = f"{tag_color}{display_tag}{reset}"
        colored_source = f"{source_color}[{entry.source}]{reset}"
        return f"{time_part}{colored_tag} {colored_source}: {formatted_message}"

    def _get_display_tag(self, extra_info: Dict[str, Any], level: LogLevel) -> str:
        msg_type = extra_info.get("type", "normal")
        if msg_type == "normal":
            return f"[{level.name}]"
        if msg_type in ("player_join", "player_leave"):
            action = "JOIN" if msg_type == "player_join" else "LEAVE"
            return f"[PLAYER_{action}]"
        return f"[{msg_type.upper()}]"

    def _get_tag_color(self, extra_info: Dict[str, Any], level: LogLevel) -> str:
        if not self.color_scheme:
            return ""
        cs = self.color_scheme
        msg_type = extra_info.get("type", "normal")
        color_map = {
            "normal": cs.get_level_color(level),
            "done": cs.done_tag,
            "success": cs.success_tag,
            "player_join": cs.player_tag,
            "player_leave": cs.player_tag,
        }
        return color_map.get(msg_type, cs.get_level_color(level))

    def _format_message_content(self, message: str, extra_info: Dict[str, Any]) -> str:
        if not self.use_colors or not self.color_scheme:
            return message
        cs = self.color_scheme
        msg_type = extra_info.get("type", "normal")

        if msg_type == "done":
            done_match = SpecialPattern.PATTERNS["done"].search(message)
            if done_match:
                start = done_match.start()
                original_done = message[start:start+4]
                return message.replace(original_done, f"{cs.done_tag}Done{cs.reset}", 1)
        elif msg_type in ("player_join", "player_leave"):
            player_name = extra_info.get("player_name")
            if player_name:
                pattern = re.compile(r"\b" + re.escape(player_name) + r"\b")
                return pattern.sub(f"{cs.player_highlight}{player_name}{cs.reset}", message)
        return message

    def format_raw_log(self, line: str) -> str:
        """格式化原始日志（无标准结构）"""
        current_time = datetime.now().strftime("%H:%M:%S")
        msg_type, extra_info = self.pattern_matcher.match(line)
        if msg_type != "normal":
            level = self.pattern_matcher.TYPE_TO_LEVEL.get(msg_type, LogLevel.RAW)
            if level.value >= self.min_level.value:
                return self._format_raw_special(line, current_time, msg_type, level, extra_info)
        if LogLevel.RAW.value >= self.min_level.value:
            return f"[{current_time}]: {line}"
        return ""

    def _format_raw_special(self, line: str, current_time: str, msg_type: str,
                            level: LogLevel, extra_info: Dict[str, Any]) -> str:
        if not self.use_colors or not self.color_scheme:
            return f"[{current_time}] [{msg_type.upper()}]: {line}"
        cs = self.color_scheme
        tag_color = self._get_tag_color(extra_info, level)
        reset = cs.reset
        formatted_line = self._format_message_content(line, extra_info)
        return f"[{current_time}] {tag_color}[{msg_type.upper()}]{reset}: {formatted_line}"


# ---------------------------------------------------------------------------
# 拓展日志接口
# ---------------------------------------------------------------------------
class ExtensionLogger:
    """供扩展使用的简易日志器，自动添加时间戳和颜色。

    用法:
        logger = ExtensionLogger("backup")
        logger.info("备份完成")
        logger.error("备份失败", exc_info=e)
    """

    __slots__ = ("_name", "_color_scheme")

    def __init__(self, name: str) -> None:
        self._name = name
        self._color_scheme: Optional[ColorScheme] = None
        if ColorSupport.supports_colors():
            self._color_scheme = ColorScheme()

    def info(self, msg: str) -> None:
        self._log("INFO", msg, LogLevel.INFO)

    def warn(self, msg: str) -> None:
        self._log("WARN", msg, LogLevel.WARN)

    def error(self, msg: str) -> None:
        self._log("ERROR", msg, LogLevel.ERROR)

    def debug(self, msg: str) -> None:
        self._log("DEBUG", msg, LogLevel.DEBUG)

    def done(self, msg: str) -> None:
        """成功/完成类消息，对标 DONE 级别。"""
        self._log("DONE", msg, LogLevel.DONE)

    def _log(self, tag: str, msg: str, level: LogLevel) -> None:
        now = datetime.now().strftime("%H:%M:%S")
        if self._color_scheme:
            cs = self._color_scheme
            lc = cs.get_level_color(level)
            nc = cs.source_tag
            rst = cs.reset
            line = (
                f"[{now}] {nc}[{self._name}]{rst} "
                f"{lc}[{tag}]{rst} {msg}"
            )
        else:
            line = f"[{now}] [{self._name}] [{tag}] {msg}"
        print(line)


# 全局默认过滤器实例
_default_filter: Optional[LogFilter] = None


def get_default_filter(min_level: LogLevel = LogLevel.INFO,
                       use_colors: Optional[bool] = None,
                       filter_sources: Optional[List[str]] = None) -> LogFilter:
    global _default_filter
    if _default_filter is None:
        _default_filter = LogFilter(min_level, use_colors, filter_sources)
    else:
        if min_level != _default_filter.min_level:
            _default_filter.min_level = min_level
        if use_colors is not None and use_colors != _default_filter.use_colors:
            _default_filter.use_colors = use_colors
            _default_filter.color_scheme = ColorScheme() if use_colors else None
        if filter_sources is not None:
            _default_filter.filter_sources = {fs.lower() for fs in filter_sources}
    return _default_filter


def parse_log_line(line: str, min_level: LogLevel = LogLevel.INFO,
                   use_colors: Optional[bool] = None,
                   filter_sources: Optional[List[str]] = None) -> Optional[str]:
    """解析并格式化日志行（同步，向后兼容）"""
    flt = get_default_filter(min_level, use_colors, filter_sources)
    entry = flt.parse_log_line(line)
    if entry and flt.should_show(entry):
        return flt.format_log(entry)
    return None


@contextmanager
def temporary_filter_config(min_level: Optional[LogLevel] = None,
                            use_colors: Optional[bool] = None,
                            filter_sources: Optional[List[str]] = None):
    """临时修改过滤器配置的上下文管理器"""
    global _default_filter
    if _default_filter is None:
        _default_filter = get_default_filter()

    original = {
        "min_level": _default_filter.min_level,
        "use_colors": _default_filter.use_colors,
        "filter_sources": _default_filter.filter_sources.copy(),
    }
    try:
        if min_level is not None:
            _default_filter.min_level = min_level
        if use_colors is not None:
            _default_filter.use_colors = use_colors
            _default_filter.color_scheme = ColorScheme() if use_colors else None
        if filter_sources is not None:
            _default_filter.filter_sources = {fs.lower() for fs in filter_sources}
        yield _default_filter
    finally:
        _default_filter.min_level = original["min_level"]
        _default_filter.use_colors = original["use_colors"]
        _default_filter.filter_sources = original["filter_sources"]
        if _default_filter.use_colors and not _default_filter.color_scheme:
            _default_filter.color_scheme = ColorScheme()
        elif not _default_filter.use_colors:
            _default_filter.color_scheme = None