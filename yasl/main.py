# . / yasl / main.py
import asyncio
import subprocess
import sys
import platform
import threading
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from yasl.log import LogFilter, LogLevel
from yasl.yasl_timer import Timer
from yasl.playtime import PlayTimeManager
import errno

# 扩展系统支持
import importlib.util

_HAS_EXTENSIONS = importlib.util.find_spec("yasl.extension_manager") is not None
if not _HAS_EXTENSIONS:
    print("Warning: extension_manager not found, extensions will not be loaded")

# 全局服务器实例引用
_current_server_instance: Optional["MinecraftServer"] = None


def get_current_server() -> Optional["MinecraftServer"]:
    """获取当前正在运行的服务器实例"""
    return _current_server_instance


class MinecraftServer:
    def __init__(
        self,
        forge_version: str = "",
        log_level: str = "INFO",
        use_colors: bool = True,
        filter_sources: Optional[List[str]] = None,
        enable_extensions: bool = True,
        enable_api: bool = False,
        api_host: str = "127.0.0.1",
        api_port: int = 8000,
    ):
        global _current_server_instance
        self.forge_version = forge_version
        self.process: Optional[subprocess.Popen] = None
        self.running = False
        self.log_filter = LogFilter(
            LogLevel.from_string(log_level), use_colors, filter_sources
        )
        self.timer = Timer()
        self.forge_path = (
            Path(__file__).parent
            / ".."
            / "server"
            / "libraries"
            / "net"
            / "minecraftforge"
            / "forge"
        )

        # 扩展管理器
        self.enable_extensions = enable_extensions and _HAS_EXTENSIONS
        self.extension_manager = None

        # API 设置
        self.api_enabled = enable_api or (os.environ.get("YASL_API_AUTOSTART") == "1")
        self.api_host = os.environ.get("YASL_API_HOST", api_host)
        self.api_port = int(os.environ.get("YASL_API_PORT", str(api_port)))
        self._api_thread: Optional[threading.Thread] = None

        # 输出控制
        self.show_all_logs = False

        # 玩家游戏时间管理器
        self.playtime_manager: Optional[PlayTimeManager] = None

        # Broken Pipe 检测和自动重启
        self._broken_pipe_check_task: Optional[asyncio.Task] = None
        self._extra_args: List[str] = []
        self._show_all_logs: bool = False
        self._is_restarting: bool = False

        # 注册为当前实例
        _current_server_instance = self
        print("[DEBUG] MinecraftServer instance created and registered globally")

    async def start(self, extra_args: List[str] = [], show_all_logs: bool = False):
        """异步启动服务器"""
        self.show_all_logs = show_all_logs
        self._extra_args = extra_args
        self._show_all_logs = show_all_logs

        # 初始化玩家游戏时间管理器
        try:
            data_file = str(Path(__file__).parent / ".." / "player_playtime.json")
            self.playtime_manager = PlayTimeManager(data_file)
            print(f"[PlayTime] Manager initialized with data file: {data_file}")
        except Exception as e:
            print(f"[PlayTime] Failed to initialize: {e}")

        # 注册服务器实例到 API
        try:
            from yasl.api import set_server

            set_server(self)
            print("[API] Server instance registered with API")
        except Exception as e:
            print(f"[API] Failed to register server instance: {e}")

        # 启动扩展管理器（在服务器启动前）
        if self.enable_extensions:
            await self._start_extensions()

        # 启动内置 API（如果配置为启用）
        if self.api_enabled:
            try:
                await self.start_api()
            except Exception as e:
                current_time = datetime.now().strftime("%H:%M:%S")
                print(f"[{current_time}] [API] Failed to start API: {e}")

        system_name = platform.system().lower()

        args = ["java"]

        args.extend(
            [
                "-Dfile.encoding=UTF-8",
                "-Dstderr.encoding=UTF-8",
                "-Dstdout.encoding=UTF-8",
            ]
        )

        args.extend(extra_args)

        if self._is_forge():
            user_jvm_arg = Path(__file__).parent / ".." / "server" / "user_jvm_args.txt"
            if user_jvm_arg.exists():
                args.append("@" + str(user_jvm_arg))

            forge_versions = [
                d for d in os.listdir(self.forge_path) if (self.forge_path / d).is_dir()
            ]
            if not forge_versions:
                raise FileNotFoundError("No Forge version directory found under forge/")
            self.forge_version = forge_versions[0]
            forge_args_file = self.forge_path / self.forge_version

            if system_name == "windows":
                forge_args_file = forge_args_file / "win_args.txt"
            elif system_name in ["linux", "darwin"]:
                forge_args_file = forge_args_file / "unix_args.txt"
            else:
                raise OSError(f"Unsupported platform: {system_name}")

            if not forge_args_file.exists():
                raise FileNotFoundError(f"Forge args file not found: {forge_args_file}")

            args.append("@" + str(forge_args_file))

        args.append("nogui")
        args.extend(sys.argv[1:])

        if not self.show_all_logs:
            print(f"Starting server with: {' '.join(args[:6])}...")
        else:
            print(f"Starting server with: {' '.join(args)}")

        self.timer.start()
        timer_msg = self.timer.format_with_current_time(
            use_colors=self.log_filter.use_colors,
            timer_color=(
                self.log_filter.colors.get("TIMER_TAG", "")
                if self.log_filter.use_colors
                else ""
            ),
            reset_color=(
                self.log_filter.colors.get("RESET", "")
                if self.log_filter.use_colors
                else ""
            ),
        )
        print(timer_msg.replace("Startup completed in", "Server startup timer started"))

        self.process = subprocess.Popen(
            args,
            cwd=str(Path(__file__).parent / ".." / "server"),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        self.running = True

        # 启动异步输出读取
        asyncio.create_task(self._read_output_async())

        print(f"[DEBUG] Server process started, PID: {self.process.pid}")

        return self.process

    async def _read_output_async(self):
        """异步读取服务器输出 - 使用批量读取优化"""
        if self.process and self.process.stdout:
            loop = asyncio.get_event_loop()
            buffer = []
            buffer_size = 10  # 批量处理大小
            flush_interval = 0.1  # 刷新间隔（秒）
            last_flush = datetime.now()
            
            while self.running:
                try:
                    # 使用线程池执行阻塞的readline操作
                    line = await loop.run_in_executor(
                        None, self.process.stdout.readline
                    )
                    if not line:
                        # 处理剩余缓冲区
                        if buffer:
                            await self._process_buffer_async(buffer)
                        break
                    
                    buffer.append(line.rstrip("\n"))
                    
                    # 检查是否需要刷新缓冲区
                    now = datetime.now()
                    should_flush = (
                        len(buffer) >= buffer_size or 
                        (now - last_flush).total_seconds() >= flush_interval
                    )
                    
                    if should_flush:
                        await self._process_buffer_async(buffer)
                        buffer.clear()
                        last_flush = now
                        
                except Exception as e:
                    print(f"Error reading output: {e}")
                    # 处理剩余缓冲区
                    if buffer:
                        await self._process_buffer_async(buffer)
                    break
    
    async def _process_buffer_async(self, lines: list):
        """批量处理日志行"""
        for line in lines:
            await self._process_log_line_async(line)

    async def _process_log_line_async(self, line: str):
        """异步处理日志行"""
        if self.show_all_logs:
            print(line)
            return

        parsed = self.log_filter.parse_log_line_tuple(line)
        if parsed:
            time, thread, source, message, level, extra_info = parsed

            # 处理玩家游戏时间统计（传递 extra_info 避免重复解析）
            if self.playtime_manager:
                try:
                    self.playtime_manager.process_log_message(message, extra_info)
                except Exception:
                    pass  # 不影响主流程

            # 异步发布日志事件到事件总线
            try:
                from yasl.event_bus import publish_async

                await publish_async(
                    "log",
                    time=time,
                    thread=thread,
                    source=source,
                    message=message,
                    level=level.name,
                    extra=extra_info,
                )
            except Exception:
                # 只记录错误，不影响主流程
                pass

            if extra_info.get("type") == "done" and not self.timer.done_received:
                self.timer.set_done(extra_info.get("time_taken", ""))
                timer_msg = self.timer.format_with_current_time(
                    use_colors=self.log_filter.use_colors,
                    timer_color=(
                        self.log_filter.colors.get("TIMER_TAG", "")
                        if self.log_filter.use_colors
                        else ""
                    ),
                    reset_color=(
                        self.log_filter.colors.get("RESET", "")
                        if self.log_filter.use_colors
                        else ""
                    ),
                )
                print(timer_msg)

            if self.log_filter.should_show_log(level, source):
                formatted = self.log_filter.format_log(
                    time, thread, source, message, level, extra_info
                )
                print(formatted)
        else:
            formatted = self.log_filter.format_raw_log(line)
            if formatted:
                print(formatted)

    async def send_command_async(self, command: str, timeout: float = 5.0) -> Optional[str]:
        """
        异步发送命令到服务器并等待结果
        
        Args:
            command: 要发送的命令
            timeout: 等待结果的超时时间（秒）
            
        Returns:
            命令执行结果，如果超时返回None
        """
        if not (self.process and self.running and self.process.stdin):
            return None
            
        from concurrent.futures import Future
        from threading import Event
        
        result_lines: List[str] = []
        future: Optional[Future] = None
        stop_event = Event()
        
        def read_output():
            """在后台线程中读取输出"""
            if not self.process or not self.process.stdout:
                return
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                return
                
            while not stop_event.is_set() and self.running:
                try:
                    # 使用非阻塞读取
                    line = self.process.stdout.readline()
                    if not line:
                        break
                    line = line.rstrip("\n")
                    result_lines.append(line)
                except Exception:
                    break
        
        try:
            # 异步写入命令
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: self._write_command(command))
            
            # 在后台线程中开始读取输出
            import threading
            reader_thread = threading.Thread(target=read_output, daemon=True)
            reader_thread.start()
            
            # 等待指定时间
            await asyncio.sleep(timeout)
            
            # 停止读取
            stop_event.set()
            reader_thread.join(timeout=1.0)
            
            if result_lines:
                return "\n".join(result_lines)
            return None
            
        except Exception as e:
            print(f"Error sending command: {e}")
            return None

    def send_command(self, command: str) -> Optional[str]:
        """同步发送命令（保持向后兼容）"""
        return self._write_command(command)

    def _write_command(self, command: str):
        """实际的命令写入逻辑"""
        if self.process and self.running and self.process.stdin:
            self.process.stdin.write(command + "\n")
            self.process.stdin.flush()

            current_time = datetime.now().strftime("%H:%M:%S")
            if self.log_filter.use_colors:
                msg = (
                    f"[{current_time}] {self.log_filter.colors.get('COMMAND_TAG', '')}[Command sent]"
                    f"{self.log_filter.colors.get('RESET', '')}: {command}"
                )
                print(msg)
            else:
                print(f"[{current_time}] [Command sent]: {command}")

    async def _start_extensions(self):
        """异步启动扩展系统"""
        try:
            # 这里应该直接使用 yasl.extension_manager
            from yasl.extension_manager import get_extension_manager

            self.extension_manager = get_extension_manager(
                extensions_dir=str(Path(__file__).parent / "extensions"),
                enable_events=True,
                debug=False,
            )

            # 注意：需要检查 extension_manager 是否有异步加载方法
            if hasattr(self.extension_manager, "load_all_extensions_async"):
                await self.extension_manager.load_all_extensions_async()
            elif hasattr(self.extension_manager, "load_all_extensions"):
                # 如果只有同步方法，在线程池中运行
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None, self.extension_manager.load_all_extensions
                )
            else:
                # 如果都没有，跳过加载
                print("[EXT] ExtensionManager has no method to load extensions.")

            # 发布服务器启动事件
            try:
                from yasl.event_bus import publish_async

                await publish_async(
                    "server.starting",
                    timestamp=datetime.now().isoformat(),
                    forge_version=self.forge_version,
                )
            except ImportError:
                pass

            current_time = datetime.now().strftime("%H:%M:%S")
            extensions_count = len(self.extension_manager.list_extensions())
            print(f"[{current_time}] [EXT] Loaded {extensions_count} extension(s)")

        except Exception as e:
            current_time = datetime.now().strftime("%H:%M:%S")
            print(f"[{current_time}] [EXT] Failed to start extensions: {e}")
            self.extension_manager = None

    # yasl/main.py (部分修复)

    async def _stop_extensions(self):
        """异步停止扩展系统"""
        if self.extension_manager:
            try:
                # 发布服务器停止事件 - 需要 await
                try:
                    from yasl.event_bus import publish_async

                    await publish_async(
                        "server.stopping", timestamp=datetime.now().isoformat()
                    )
                except ImportError:
                    pass

                # 停止扩展管理器
                if hasattr(self.extension_manager, "shutdown_async"):
                    await self.extension_manager.shutdown_async()
                else:
                    # 如果只有同步方法
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, self.extension_manager.shutdown)

                current_time = datetime.now().strftime("%H:%M:%S")
                print(f"[{current_time}] [EXT] Extensions stopped")

            except Exception as e:
                current_time = datetime.now().strftime("%H:%M:%S")
                print(f"[{current_time}] [EXT] Error stopping extensions: {e}")

    async def start_api(self):
        """异步启动API"""
        if self._api_thread and self._api_thread.is_alive():
            return

        try:
            from yasl import api as yasl_api

            await yasl_api.start_api(self.api_host, self.api_port)
            # 标记为已启动
            self._api_thread = threading.Thread(target=lambda: None, daemon=True)
            self._api_thread.start()
            current_time = datetime.now().strftime("%H:%M:%S")
            print(f"[{current_time}] [API] Started on {self.api_host}:{self.api_port}")
        except Exception as e:
            current_time = datetime.now().strftime("%H:%M:%S")
            print(f"[{current_time}] [API] Error starting API: {e}")

    async def stop_api(self):
        """异步停止API"""
        try:
            from yasl import api as yasl_api

            await yasl_api.stop_api()
            current_time = datetime.now().strftime("%H:%M:%S")
            print(f"[{current_time}] [API] stop requested")
        except Exception as e:
            current_time = datetime.now().strftime("%H:%M:%S")
            print(f"[{current_time}] [API] Error requesting stop: {e}")

    async def stop(self):
        """异步停止服务器"""
        if self.process and self.running:
            current_time = datetime.now().strftime("%H:%M:%S")
            print(f"[{current_time}] Stopping server...")

            # 停止扩展
            await self._stop_extensions()

            # 发送停止命令
            try:
                await self.send_command_async("stop")
            except Exception as e:
                print(f"[{current_time}] Error sending stop command: {e}")

            try:
                # 异步等待进程结束
                loop = asyncio.get_event_loop()
                await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: self.process.wait(timeout=30)),
                    timeout=35,
                )
            except (asyncio.TimeoutError, subprocess.TimeoutExpired):
                current_time = datetime.now().strftime("%H:%M:%S")
                print(
                    f"[{current_time}] Server did not stop gracefully, forcing termination..."
                )
                if self.process:
                    self.process.terminate()
                    try:
                        await loop.run_in_executor(None, self.process.wait)
                    except Exception:
                        pass
            except Exception as e:
                print(f"[{current_time}] Error waiting for process: {e}")
            finally:
                self.running = False

            # 移除pid文件
            try:
                pid_file = Path(__file__).parent / "server_pid.txt"
                if pid_file.exists():
                    pid_file.unlink()
            except Exception:
                pass

            # 尝试停止内置API
            try:
                await self.stop_api()
            except Exception:
                pass

            # 保存玩家游戏时间数据
            if self.playtime_manager:
                try:
                    self.playtime_manager.shutdown()
                except Exception:
                    pass

            print(f"[{current_time}] Server stopped")

    def _is_forge(self) -> bool:
        """检查是否为Forge服务器"""
        return self.forge_path.exists()

    def check_broken_pipe(self) -> bool:
        """
        检测是否存在 Broken Pipe
        
        Returns:
            True 如果检测到 broken pipe，False 如果正常
        """
        if not self.process or not self.running:
            return False
        
        # 检查进程是否已经结束
        if self.process.poll() is not None:
            return True
        
        # 检查 stdin 是否可用
        if not self.process.stdin:
            return True
        
        try:
            # 尝试写入空命令来检测 pipe 是否断开
            # 使用非阻塞方式检测
            self.process.stdin.write("")
            self.process.stdin.flush()
            return False
        except BrokenPipeError:
            return True
        except OSError as e:
            if e.errno in (errno.EPIPE, errno.ESHUTDOWN, errno.ECONNRESET):
                return True
            return False
        except Exception:
            return False

    async def start_broken_pipe_monitor(self, interval: float = 10.0):
        """
        启动 Broken Pipe 监控任务
        
        Args:
            interval: 检测间隔（秒），默认10秒
        """
        if self._broken_pipe_check_task and not self._broken_pipe_check_task.done():
            return  # 已经在运行
        
        self._broken_pipe_check_task = asyncio.create_task(
            self._broken_pipe_monitor_loop(interval)
        )

    async def stop_broken_pipe_monitor(self):
        """停止 Broken Pipe 监控任务"""
        if self._broken_pipe_check_task and not self._broken_pipe_check_task.done():
            self._broken_pipe_check_task.cancel()
            try:
                await self._broken_pipe_check_task
            except asyncio.CancelledError:
                pass

    async def _broken_pipe_monitor_loop(self, interval: float):
        """
        Broken Pipe 监控循环
        
        Args:
            interval: 检测间隔（秒）
        """
        while self.running:
            try:
                await asyncio.sleep(interval)
                
                if not self.running:
                    break
                
                if self.check_broken_pipe():
                    current_time = datetime.now().strftime("%H:%M:%S")
                    print(f"[{current_time}] [BrokenPipe] 检测到 Broken Pipe，正在自动重启服务器...")
                    
                    # 执行自动重启
                    await self._auto_restart_server()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                # 静默处理异常，不影响主流程
                pass

    async def _auto_restart_server(self):
        """自动重启服务器"""
        if self._is_restarting:
            return  # 防止重复重启
        
        self._is_restarting = True
        
        try:
            current_time = datetime.now().strftime("%H:%M:%S")
            
            # 1. 停止当前进程（如果还在运行）
            if self.process and self.process.poll() is None:
                try:
                    self.process.terminate()
                    # 等待进程结束
                    loop = asyncio.get_event_loop()
                    await asyncio.wait_for(
                        loop.run_in_executor(None, self.process.wait),
                        timeout=10.0
                    )
                except Exception:
                    if self.process:
                        try:
                            self.process.kill()
                        except Exception:
                            pass
            
            self.running = False
            
            # 2. 保存玩家数据
            if self.playtime_manager:
                try:
                    self.playtime_manager.shutdown()
                except Exception:
                    pass
            
            # 3. 重新初始化 Timer
            self.timer = Timer()
            
            # 4. 重新启动服务器
            print(f"[{current_time}] [BrokenPipe] 正在重新启动服务器...")
            
            await self.start(
                extra_args=self._extra_args,
                show_all_logs=self._show_all_logs
            )
            
            current_time = datetime.now().strftime("%H:%M:%S")
            print(f"[{current_time}] [BrokenPipe] 服务器重启完成，新 PID: {self.process.pid if self.process else 'N/A'}")
            
        except Exception as e:
            current_time = datetime.now().strftime("%H:%M:%S")
            print(f"[{current_time}] [BrokenPipe] 自动重启失败: {e}")
        finally:
            self._is_restarting = False
