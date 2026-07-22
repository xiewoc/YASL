# . / yasl / main.py
import asyncio
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, List
from yasl.loader import Load
from yasl.logging import LogLevel, LogFilter, ExtensionLogger

_log = ExtensionLogger("Server")


class MinecraftServer:
    def __init__(
        self,
        forge_version: str = "",
        log_level: str = "INFO",
        use_colors: bool = True,
        filter_sources: Optional[List[str]] = None,
        load: Optional[Load] = None,
        server_path: Optional[Path] = None,
        server_type: str = ""
    ):
        if load is None:
            load = Load(forge_version=forge_version, server_type=server_type)
        if server_path is None:
            server_path = load.serverfile_path()
        self.load = load
        self.server_path = server_path if server_path is not None else Path("")

        parsed_level = LogLevel.from_string(log_level)
        self.log_filter = LogFilter(
            min_level=parsed_level,
            use_colors=use_colors,
            filter_sources=filter_sources,
        )

        self.process: Optional[subprocess.Popen] = None
        self.running: bool = False
        self._show_all_logs: bool = False
        self._read_task: Optional[asyncio.Task] = None

        self._broken_pipe_check_task: Optional[asyncio.Task] = None
        self._extra_args: List[str] = []
        self._is_restarting: bool = False

        # 命令输出收集器（asyncio.Queue 列表，send_command_async 使用）
        self._command_collectors: list = []

    # ------------------------------------------------------------------
    # 启动 / 停止
    # ------------------------------------------------------------------

    async def start(self, extra_args: List[str] = [], show_all_logs: bool = False):
        """异步启动服务器"""
        self._extra_args = extra_args
        self._show_all_logs = show_all_logs
        # 清空上次遗留的命令收集器
        self._command_collectors.clear()

        args = ["java"]
        args.extend([
            "-Dfile.encoding=UTF-8",
            "-Dstderr.encoding=UTF-8",
            "-Dstdout.encoding=UTF-8",
            "-Dfml.ignoreInvalidMinecraftCertificates=true",
            "-Dfml.ignorePatchDiscrepancies=true",
        ])

        server_type = self.load.server_type()
        if server_type == "forge":
            user_jvm_arg = Path(__file__).parent / ".." / "server" / "user_jvm_args.txt"
            if user_jvm_arg.exists():
                args.append("@" + str(user_jvm_arg))

            # extra_args 必须在 @unix_args.txt 之前，否则会被当作程序参数
            # 放在 @user_jvm_args.txt 之后可覆盖其中的 -Xms/-Xmx
            args.extend(extra_args)

            forge_dir = self.load.forge_path
            if forge_dir and forge_dir.is_dir():
                args_file = forge_dir / ("win_args.txt" if sys.platform == "win32" else "unix_args.txt")
                if args_file.exists():
                    args.append("@" + str(args_file))
        elif server_type == "paper":
            if self.load.paper_path and self.load.paper_path.is_file():
                args.extend(["-jar", str(self.load.paper_path)])

        args.append("nogui")

        print(
            f"Starting server with: {' '.join(args[:6])}..."
            if not self._show_all_logs
            else f"Starting server with: {' '.join(args)}"
        )

        loop = asyncio.get_running_loop()
        self.process = await loop.run_in_executor(
            None,
            lambda: subprocess.Popen(
                args,
                cwd=str(Path(__file__).parent / ".." / "server"),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            ),
        )

        self.running = True
        self._read_task = asyncio.create_task(self._read_output_async())
        assert self.process is not None
        print(f"[DEBUG] 服务器已启动, PID: {self.process.pid}")
        return self.process

    async def stop(self):
        self.running = False
        await self.stop_broken_pipe_monitor()

        if not self.process:
            return

        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] [YASL] 正在停止服务器...")

        try:
            await self.send_command_async("stop", timeout=3.0)
        except Exception:
            pass

        loop = asyncio.get_running_loop()
        try:
            await asyncio.wait_for(
                loop.run_in_executor(None, self._process_wait, 30),
                timeout=35,
            )
        except (asyncio.TimeoutError, subprocess.TimeoutExpired):
            print(f"[{ts}] [YASL] 服务器未响应，强制终止...")
            await self._force_kill_async()
        except Exception:
            await self._force_kill_async()
        finally:
            if self.process:
                try:
                    await loop.run_in_executor(None, self.process.wait)
                except Exception:
                    pass

        if self._read_task and not self._read_task.done():
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass

        await self._cleanup_resources_async(ts)

    def _process_wait(self, timeout: int):
        if self.process:
            self.process.wait(timeout=timeout)

    async def _force_kill_async(self):
        if not self.process:
            return
        loop = asyncio.get_running_loop()
        for action in ("terminate", "kill"):
            try:
                await loop.run_in_executor(None, getattr(self.process, action))
            except Exception:
                pass

    async def _cleanup_resources_async(self, ts: str):
        loop = asyncio.get_running_loop()

        await loop.run_in_executor(None, lambda: _unlink_pid(Path(__file__).parent))

        proc = self.process
        if proc:
            await loop.run_in_executor(None, lambda: _close_streams(proc))
        print(f"[{ts}] [YASL] 服务器已停止")

    # ------------------------------------------------------------------
    # 输出读取
    # ------------------------------------------------------------------

    async def _read_output_async(self):
        if not (self.process and self.process.stdout):
            return
        loop = asyncio.get_running_loop()
        buf: list[str] = []
        SIZE, INTERVAL = 10, 0.1
        last = datetime.now()

        while self.running:
            try:
                line = await asyncio.wait_for(
                    loop.run_in_executor(None, self.process.stdout.readline),
                    timeout=5.0,
                )
                if not line:
                    if buf:
                        await self._process_buffer_async(buf)
                    break
                buf.append(line.rstrip("\n"))
                now = datetime.now()
                if len(buf) >= SIZE or (now - last).total_seconds() >= INTERVAL:
                    await self._process_buffer_async(buf)
                    buf.clear()
                    last = now
            except asyncio.TimeoutError:
                # readline 在 5 秒内未返回完整行（可能遇到 \r 结尾的进度条等）
                # 继续等待，不中断循环
                if buf:
                    await self._process_buffer_async(buf)
                    buf.clear()
                    last = datetime.now()
                continue
            except Exception as e:
                print(f"Error reading output: {e}")
                if buf:
                    await self._process_buffer_async(buf)
                break

    async def _process_buffer_async(self, lines: list):
        for line in lines:
            await self._process_log_line_async(line)

    async def _process_log_line_async(self, line: str):
        # 将原始行推送到所有活跃的命令收集器
        for q in self._command_collectors:
            try:
                q.put_nowait(line)
            except asyncio.QueueFull:
                pass

        entry = self.log_filter.parse_log_line(line)
        if entry and self.log_filter.should_show(entry):
            formatted = self.log_filter.format_log(entry)
            if formatted:
                print(formatted)
                return
        raw = self.log_filter.format_raw_log(line)
        if raw:
            print(raw)

    # ------------------------------------------------------------------
    # 命令接口
    # ------------------------------------------------------------------

    async def send_command_async(self, command: str, timeout: float = 5.0) -> Dict[str, Any]:
        """向服务器发送命令并收集响应行。

        使用 asyncio.Queue 从主日志管道收集输出，不再创建竞争读取线程。
        """
        if not (self.process and self.running and self.process.stdin):
            return {"lines": [], "timed_out": False, "count": 0}

        result_lines: List[str] = []
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._command_collectors.append(q)

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._write_command_sync, command)

            deadline = loop.time() + timeout
            idle_ticks = 0
            TICK = 0.1
            IDLE_MAX = 8  # 0.8 秒无新输出即认为命令执行完毕

            while loop.time() < deadline:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                try:
                    line = await asyncio.wait_for(q.get(), timeout=min(TICK, remaining))
                    result_lines.append(line.rstrip("\n") if line.endswith("\n") else line)
                    idle_ticks = 0
                except asyncio.TimeoutError:
                    if result_lines:
                        idle_ticks += 1
                        if idle_ticks >= IDLE_MAX:
                            break

            return {
                "lines": list(result_lines),
                "timed_out": loop.time() >= deadline and len(result_lines) == 0,
                "count": len(result_lines),
            }
        except Exception as e:
            print(f"Error sending command: {e}")
            return {"lines": [], "timed_out": False, "count": 0}
        finally:
            try:
                self._command_collectors.remove(q)
            except ValueError:
                pass

    def send_command(self, command: str) -> Optional[str]:
        if self.process and self.running and self.process.stdin:
            self._write_command_sync(command)
        return None

    def _write_command_sync(self, command: str):
        proc = self.process
        if proc and self.running and proc.stdin:
            proc.stdin.write(command + "\n")
            proc.stdin.flush()
            print(f"[{datetime.now():%H:%M:%S}] [Command sent]: {command}")

    # ------------------------------------------------------------------
    # Broken Pipe 检测 & 自动重启
    # ------------------------------------------------------------------

    async def check_broken_pipe_async(self) -> bool:
        if not self.process or not self.running:
            return False
        if self.process.poll() is not None or not self.process.stdin:
            return True

        def _try_write():
            proc = self.process
            if not proc or not proc.stdin:
                return True
            try:
                proc.stdin.write("")
                proc.stdin.flush()
                return False
            except (BrokenPipeError, OSError):
                raise

        try:
            return await asyncio.get_running_loop().run_in_executor(None, _try_write)
        except Exception:
            return True

    async def start_broken_pipe_monitor(self, interval: float = 10.0):
        if self._broken_pipe_check_task and not self._broken_pipe_check_task.done():
            return
        self._broken_pipe_check_task = asyncio.create_task(
            self._broken_pipe_monitor_loop(interval)
        )

    async def stop_broken_pipe_monitor(self):
        if self._broken_pipe_check_task and not self._broken_pipe_check_task.done():
            self._broken_pipe_check_task.cancel()
            try:
                await self._broken_pipe_check_task
            except asyncio.CancelledError:
                pass

    async def _broken_pipe_monitor_loop(self, interval: float):
        while self.running:
            try:
                await asyncio.sleep(interval)
                if not self.running:
                    break
                if await self.check_broken_pipe_async():
                    ts = datetime.now().strftime("%H:%M:%S")
                    print(f"[{ts}] [BrokenPipe] 检测到断连，正在重启...")
                    await self._auto_restart_server()
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    async def _auto_restart_server(self):
        if self._is_restarting:
            return
        self._is_restarting = True
        try:
            ts = datetime.now().strftime("%H:%M:%S")
            if self.process and self.process.poll() is None:
                loop = asyncio.get_running_loop()
                try:
                    await loop.run_in_executor(None, self.process.terminate)
                    await asyncio.wait_for(
                        loop.run_in_executor(None, self.process.wait), timeout=10.0
                    )
                except Exception:
                    if self.process:
                        try:
                            await loop.run_in_executor(None, self.process.kill)
                        except Exception:
                            pass
            self.running = False
            print(f"[{ts}] [BrokenPipe] 正在重启...")
            await self.start(extra_args=self._extra_args, show_all_logs=self._show_all_logs)
            print(
                f"[{datetime.now():%H:%M:%S}] [BrokenPipe] 重启完成, "
                f"PID: {self.process.pid if self.process else 'N/A'}"
            )
        except Exception as e:
            print(f"[{datetime.now():%H:%M:%S}] [BrokenPipe] 重启失败: {e}")
        finally:
            self._is_restarting = False


# ---------------------------------------------------------------------------
# 模块级工具（供 run_in_executor 调用）
# ---------------------------------------------------------------------------
def _unlink_pid(parent: Path) -> None:
    try:
        (parent / "server_pid.txt").unlink(missing_ok=True)
    except Exception:
        pass


def _close_streams(proc: subprocess.Popen) -> None:
    for attr in ("stdout", "stderr", "stdin"):
        try:
            s = getattr(proc, attr, None)
            if s:
                s.close()
        except Exception:
            pass