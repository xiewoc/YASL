"""
实时监控模块

包含服务器进程实时监控图表类
"""
import time
from typing import Optional

# 全局变量，用于延迟导入检查
_HAS_MATPLOTLIB = False
_HAS_PSUTIL = False


def _check_dependencies():
    """检查依赖并返回状态"""
    global _HAS_MATPLOTLIB, _HAS_PSUTIL
    
    if _HAS_MATPLOTLIB and _HAS_PSUTIL:
        return True
    
    # 导入 matplotlib
    try:
        import matplotlib.pyplot as plt
        import matplotlib.animation as animation
        from matplotlib import style
        style.use("dark_background")
        _HAS_MATPLOTLIB = True
    except ImportError:
        print("警告: matplotlib 未安装，实时监控功能不可用")
        print("安装: pip install matplotlib")
        _HAS_MATPLOTLIB = False

    # 导入 psutil
    try:
        import psutil
        _HAS_PSUTIL = True
    except ImportError:
        print("警告: psutil 未安装，系统监控功能有限")
        print("安装: pip install psutil")
        _HAS_PSUTIL = False
    
    return _HAS_MATPLOTLIB and _HAS_PSUTIL


class RealTimeMonitor:
    """实时监控图表类"""
    
    def __init__(self, server_process, refresh_interval: float = 0.05):
        """初始化实时监控器"""
        if not _check_dependencies():
            raise ImportError("依赖库未安装")
        
        # 延迟导入 matplotlib 和 psutil
        import matplotlib.pyplot as plt
        import matplotlib.animation as animation
        from matplotlib import style
        
        self._plt = plt
        self._animation = animation
        self._style = style
        
        self.server_process = server_process
        self.refresh_interval = refresh_interval
        self.running = False

        # 数据存储（保留最近60秒的数据）
        self.timestamps = []
        self.cpu_usage = []
        self.memory_gb = []

        # 图表设置
        self.fig, (self.ax1, self.ax2) = plt.subplots(2, 1, figsize=(10, 8))
        self.fig.canvas.manager.set_window_title("Minecraft Server Monitor - Real Time")
        self.fig.patch.set_facecolor("#1e1e1e")

        # 初始化图表
        self._setup_charts()

        # 动画对象
        self.ani: Optional[object] = None

    def _setup_charts(self):
        """设置图表样式"""
        # CPU使用率图表
        self.ax1.set_facecolor("#2d2d2d")
        self.ax1.set_title("CPU Usage (%) - Real Time", color="white", fontsize=12, pad=10)
        self.ax1.set_ylabel("CPU %", color="cyan", fontsize=10)
        self.ax1.set_ylim(0, 100)
        self.ax1.grid(True, alpha=0.3, linestyle="--", linewidth=0.5)

        # 内存使用图表
        self.ax2.set_facecolor("#2d2d2d")
        self.ax2.set_title("Memory Usage (GB) - Real Time", color="white", fontsize=12, pad=10)
        self.ax2.set_ylabel("Memory (GB)", color="magenta", fontsize=10)
        self.ax2.set_xlabel("Time (seconds ago)", color="white", fontsize=10)
        self.ax2.grid(True, alpha=0.3, linestyle="--", linewidth=0.5)

        # 调整布局
        self.fig.tight_layout(pad=3.0)

    def get_process_usage_sync(self):
        """同步获取进程使用情况"""
        if not self.server_process or self.server_process.poll() is not None:
            return 0, 0

        import psutil
        
        cpu_percent = 0
        memory_gb = 0

        try:
            proc = psutil.Process(self.server_process.pid)
            children = proc.children(recursive=True)
            all_processes = [proc] + children

            total_cpu = 0
            total_memory = 0

            for p in all_processes:
                try:
                    cpu = p.cpu_percent(interval=0.01)
                    total_cpu += cpu

                    mem_info = p.memory_info()
                    total_memory += mem_info.rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            cpu_percent = min(total_cpu, 100)
            memory_gb = total_memory / (1024**3)

        except Exception as e:
            print(f"[Monitor] Error getting process usage: {e}")

        return cpu_percent, memory_gb

    def update_chart(self, frame):
        """更新图表数据"""
        if not self.running:
            return

        try:
            cpu, memory_gb = self.get_process_usage_sync()
            current_time = time.time()

            self.timestamps.append(current_time)
            self.cpu_usage.append(cpu)
            self.memory_gb.append(memory_gb)

            max_points = int(60 / self.refresh_interval)
            if len(self.timestamps) > max_points:
                self.timestamps.pop(0)
                self.cpu_usage.pop(0)
                self.memory_gb.pop(0)

            if len(self.timestamps) < 2:
                return

            time_ago = [current_time - t for t in self.timestamps]

            # 更新CPU图表
            self.ax1.clear()
            self.ax1.set_facecolor("#2d2d2d")
            self.ax1.set_title(f"CPU Usage: {cpu:.1f}% - Real Time", color="white", fontsize=12, pad=10)
            self.ax1.set_ylabel("CPU %", color="cyan", fontsize=10)
            self.ax1.set_ylim(0, max(100, max(self.cpu_usage) * 1.1) if self.cpu_usage else 100)
            self.ax1.set_xlim(max(time_ago), min(time_ago))
            self.ax1.grid(True, alpha=0.3, linestyle="--", linewidth=0.5)
            self.ax1.plot(time_ago, self.cpu_usage, color="cyan", linewidth=2, label=f"CPU: {cpu:.1f}%")
            self.ax1.fill_between(time_ago, self.cpu_usage, 0, color="cyan", alpha=0.3)
            self.ax1.legend(loc="upper right", facecolor="#2d2d2d", edgecolor="white")

            # 更新内存图表
            self.ax2.clear()
            self.ax2.set_facecolor("#2d2d2d")
            self.ax2.set_title(f"Memory Usage: {memory_gb:.2f} GB", color="white", fontsize=12, pad=10)
            self.ax2.set_ylabel("Memory (GB)", color="magenta", fontsize=10)
            self.ax2.set_xlabel("Time (seconds ago)", color="white", fontsize=10)
            self.ax2.set_ylim(0, max(1, max(self.memory_gb) * 1.1) if self.memory_gb else 1)
            self.ax2.set_xlim(max(time_ago), min(time_ago))
            self.ax2.grid(True, alpha=0.3, linestyle="--", linewidth=0.5)
            self.ax2.plot(time_ago, self.memory_gb, color="magenta", linewidth=2, label=f"Memory: {memory_gb:.2f} GB")
            self.ax2.fill_between(time_ago, self.memory_gb, 0, color="magenta", alpha=0.3)
            self.ax2.legend(loc="upper right", facecolor="#2d2d2d", edgecolor="white")

            self.fig.tight_layout(rect=[0, 0.03, 1, 0.97])

        except Exception as e:
            print(f"[Monitor] Chart update error: {e}")

    def start(self):
        """启动监控"""
        self.running = True
        if not self.ani:
            self.ani = self._animation.FuncAnimation(
                self.fig, self.update_chart,
                interval=int(self.refresh_interval * 1000),
                cache_frame_data=False,
            )
        self._plt.ion()
        self._plt.show(block=False)
        print(f"实时监控图表已启动 ({self.refresh_interval*1000:.0f}ms刷新)")

    def stop(self):
        """停止监控"""
        self.running = False
        if self.ani:
            self.ani.event_source.stop()
        if self._plt.fignum_exists(self.fig.number):
            self._plt.close(self.fig)
        print("实时监控图表已停止")


# 导出模块接口
__all__ = ['RealTimeMonitor', '_check_dependencies', '_HAS_MATPLOTLIB', '_HAS_PSUTIL']