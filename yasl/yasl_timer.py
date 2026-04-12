# timer.py
import time
from datetime import datetime


class Timer:
    def __init__(self):
        self.start_time = None
        self.done_time = None
        self.server_time = None
        self.done_received = False

    def start(self):
        self.start_time = time.time()

    def set_done(self, server_time_str: str):
        if not self.done_received:
            self.done_received = True
            self.done_time = time.time()
            try:
                # 去除字符串末尾的 's' 并转换为浮点数
                seconds = float(server_time_str.rstrip("s"))
                self.server_time = seconds
            except ValueError:
                self.server_time = None

    def get_elapsed(self) -> float:
        if self.start_time is None:
            return 0.0
        if self.done_time is not None:
            return self.done_time - self.start_time
        return time.time() - self.start_time

    def format_time(self, seconds: float) -> str:
        """格式化时间间隔为易读的字符串"""
        if seconds < 60:
            return f"{seconds:.2f}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            remaining_seconds = seconds % 60
            return f"{minutes}m {remaining_seconds:.2f}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            remaining_seconds = seconds % 60
            return f"{hours}h {minutes}m {remaining_seconds:.2f}s"

    def format_with_current_time(
        self, use_colors: bool = True, timer_color: str = "", reset_color: str = ""
    ) -> str:
        """格式化带当前时间的计时器输出"""
        current_time = datetime.now().strftime("%H:%M:%S")
        elapsed = self.get_elapsed()

        if self.server_time is not None:
            message = f"Startup completed in {self.format_time(elapsed)} (server reported: {self.server_time:.3f}s)"
        else:
            message = f"Startup completed in {self.format_time(elapsed)}"

        if use_colors:
            return f"[{current_time}] {timer_color}[TIMER]{reset_color}: {message}"
        else:
            return f"[{current_time}] [TIMER]: {message}"

    def is_running(self) -> bool:
        """检查计时器是否正在运行"""
        return self.start_time is not None and self.done_time is None

    def is_finished(self) -> bool:
        """检查计时是否已完成"""
        return self.done_time is not None

    def reset(self):
        """重置计时器"""
        self.start_time = None
        self.done_time = None
        self.server_time = None
        self.done_received = False
