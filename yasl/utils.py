"""
YASL 公共工具模块

包含项目中使用的公共工具函数和常量
"""

import os
import sys
import platform
from datetime import datetime
from typing import Optional, Dict, Any

# ============ 时间工具 ============

def get_timestamp(fmt: str = "%H:%M:%S") -> str:
    """获取当前时间戳字符串"""
    return datetime.now().strftime(fmt)


def get_iso_timestamp() -> str:
    """获取 ISO 格式时间戳"""
    return datetime.now().isoformat()


def format_duration(seconds: int) -> str:
    """格式化时长为可读字符串"""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours}小时{minutes}分钟{secs}秒"


# ============ 颜色工具 ============

class Colors:
    """ANSI 颜色代码集合"""
    
    # 重置
    RESET = "\033[0m"
    
    # 基础颜色
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    
    # 亮色
    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"
    
    # 256色模式
    @staticmethod
    def color256(code: int) -> str:
        """返回 256 色代码"""
        return f"\033[38;5;{code}m"
    
    # 真彩色模式
    @staticmethod
    def rgb(r: int, g: int, b: int) -> str:
        """返回 RGB 真彩色代码"""
        return f"\033[38;2;{r};{g};{b}m"


def supports_color() -> bool:
    """检测终端是否支持颜色输出"""
    # 检查环境变量
    if "NO_COLOR" in os.environ:
        return False
    
    if "FORCE_COLOR" in os.environ:
        return True
    
    # 检查是否在终端中
    if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
        return False
    
    # Windows 平台需要特殊处理
    if platform.system().lower() == "windows":
        return _enable_windows_vt()
    
    return True


def _enable_windows_vt() -> bool:
    """启用 Windows 虚拟终端支持"""
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


# ============ 日志工具 ============

def log_print(message: str, level: str = "INFO", prefix: str = "", use_color: bool = True):
    """
    统一的日志打印函数
    
    Args:
        message: 日志消息
        level: 日志级别 (INFO, WARN, ERROR, DEBUG)
        prefix: 前缀标签
        use_color: 是否使用颜色
    """
    timestamp = get_timestamp()
    
    if use_color and supports_color():
        level_colors = {
            "INFO": Colors.BRIGHT_GREEN,
            "WARN": Colors.BRIGHT_YELLOW,
            "ERROR": Colors.BRIGHT_RED,
            "DEBUG": Colors.BRIGHT_BLACK,
        }
        level_color = level_colors.get(level, Colors.WHITE)
        
        if prefix:
            print(f"[{timestamp}] {level_color}[{prefix}]{Colors.RESET} {message}")
        else:
            print(f"[{timestamp}] {level_color}[{level}]{Colors.RESET} {message}")
    else:
        if prefix:
            print(f"[{timestamp}] [{prefix}] {message}")
        else:
            print(f"[{timestamp}] [{level}] {message}")


# ============ 系统工具 ============

def ensure_dir(path: str) -> bool:
    """确保目录存在，不存在则创建"""
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except Exception:
        return False


def get_project_root() -> str:
    """获取项目根目录"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ============ Minecraft 相关正则表达式 ============

import re

# 玩家相关模式
PLAYER_PATTERNS = {
    "chat": re.compile(r"^<(\w{1,16})>\s+(.+)$"),
    "join": re.compile(r"^(\w{1,16})\s+joined the game$", re.IGNORECASE),
    "leave_left": re.compile(r"^(\w{1,16})\s+left the game$", re.IGNORECASE),
    "leave_lost": re.compile(r"^(\w{1,16})\s+lost connection:\s*(.*)$", re.IGNORECASE),
    "command": re.compile(r"^(\w{1,16})\s+(?:issued server command|executed):?\s+(/.+)$", re.IGNORECASE),
}

# 服务器生命周期模式
SERVER_PATTERNS = {
    "done": re.compile(r"^Done\s*\((\d+\.\d+s)\)!.*$", re.IGNORECASE),
    "preparing": re.compile(r"^Preparing spawn area:\s*(\d+)%.*$", re.IGNORECASE),
    "starting": re.compile(r"^Starting Minecraft server on .*$", re.IGNORECASE),
    "stopping": re.compile(r"^Stopping server.*$", re.IGNORECASE),
    "started": re.compile(r"^.*server.*started.*$", re.IGNORECASE),
    "cant_keep_up": re.compile(
        r"Can't keep up! Is the server overloaded\? Running\s*(\d+)ms or\s*(\d+) ticks behind",
        re.IGNORECASE,
    ),
}

# 日志行模式
LOG_PATTERN = re.compile(
    r"(?:\[(?P<time>[^\]]+)\]\s*)?"
    r"\[(?P<thread>[^\/]+)\/(?P<level>[A-Za-z]+)\]\s*"
    r"(?:\[(?P<source>[^\]]+)\]\s*:?\s*)?"
    r"(?P<message>.*)"
)


# ============ 导出 ============

__all__ = [
    # 时间工具
    "get_timestamp",
    "get_iso_timestamp",
    "format_duration",
    # 颜色工具
    "Colors",
    "supports_color",
    # 日志工具
    "log_print",
    # 系统工具
    "ensure_dir",
    "get_project_root",
    # 正则表达式
    "PLAYER_PATTERNS",
    "SERVER_PATTERNS",
    "LOG_PATTERN",
]