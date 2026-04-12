"""
命令解析和指令处理模块

将命令行参数解析和运行时命令处理从 run.py 中分离出来
"""
import asyncio
import argparse
import subprocess
import sys

# 尝试导入 psutil（用于内存/CPU 监控）
try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="Minecraft Server Launcher")

    # 日志设置
    parser.add_argument(
        "--log-level",
        type=str,
        default="WARN",
        choices=["RAW", "INFO", "WARN", "ERROR", "FATAL", "DONE"],
        help="Minimum log level to display",
    )

    parser.add_argument(
        "--show-all",
        action="store_true",
        help="Show all raw log output without filtering",
    )

    parser.add_argument(
        "--no-colors", action="store_true", help="Disable colored output"
    )

    # 扩展设置
    parser.add_argument(
        "--no-extensions", action="store_true", help="Disable extensions"
    )

    # JVM 参数
    parser.add_argument(
        "--no-jvm-optimize",
        action="store_true",
        help="Disable automatic JVM optimization",
    )

    parser.add_argument(
        "--minimal-jvm", action="store_true", help="Use minimal JVM arguments"
    )

    parser.add_argument("--jvm-memory-min", type=int, help="Minimum JVM memory in GB")

    parser.add_argument("--jvm-memory-max", type=int, help="Maximum JVM memory in GB")

    # 监控设置
    parser.add_argument(
        "--monitor", action="store_true", help="Enable real-time monitoring chart"
    )

    parser.add_argument(
        "--refresh-rate", type=float, default=0.05, help="Chart refresh rate in seconds"
    )

    # 解析参数
    args, remaining_args = parser.parse_known_args()
    sys.argv = [sys.argv[0]] + remaining_args

    return args


async def get_process_info_async(process, info_type="memory"):
    """异步获取进程信息"""
    if not _HAS_PSUTIL:
        return "psutil 未安装，无法获取进程信息"
    
    if not process or process.poll() is not None:
        return "进程未运行"

    try:
        loop = asyncio.get_event_loop()
        proc = await loop.run_in_executor(None, lambda: psutil.Process(process.pid))
        children = await loop.run_in_executor(
            None, lambda: proc.children(recursive=True)
        )

        if not children:
            return "无子进程"

        output_lines = ["子进程信息:"]
        total_value = 0

        for child in children:
            try:
                if info_type == "memory":
                    mem_info = await loop.run_in_executor(
                        None, lambda c=child: c.memory_info()
                    )
                    value = mem_info.rss / (1024 * 1024)  # MB
                    percent = await loop.run_in_executor(
                        None, lambda c=child: c.memory_percent()
                    )
                    output_lines.append(
                        f"  PID={child.pid} name={child.name()} RSS={value:.1f}MB ({percent:.1f}%)"
                    )
                    total_value += value
                elif info_type == "cpu":
                    # 初始化 CPU 计数器
                    await loop.run_in_executor(
                        None, lambda c=child: c.cpu_percent(None)
                    )
                    await asyncio.sleep(0.1)
                    cpu = await loop.run_in_executor(
                        None, lambda c=child: c.cpu_percent(None)
                    )
                    output_lines.append(
                        f"  PID={child.pid} name={child.name()} CPU={cpu:.1f}%"
                    )
                    total_value += cpu
            except Exception as e:
                output_lines.append(f"  PID={child.pid} error: {str(e)[:50]}")

        if info_type == "memory":
            output_lines.append(f"总内存: {total_value:.1f}MB")
        elif info_type == "cpu":
            output_lines.append(f"总CPU: {total_value:.1f}%")

        return "\n".join(output_lines)

    except Exception as e:
        return f"获取信息失败: {e}"


async def get_system_info_async():
    """异步获取系统信息"""
    if not _HAS_PSUTIL:
        return None, None
    
    try:
        loop = asyncio.get_event_loop()
        cpu = await loop.run_in_executor(
            None, lambda: psutil.cpu_percent(interval=0.5)
        )
        mem = await loop.run_in_executor(
            None, lambda: psutil.virtual_memory()
        )
        return cpu, mem
    except Exception as e:
        print(f"获取系统信息失败: {e}")
        return None, None


async def handle_user_input(server, monitor, extra_jvm_args, has_matplotlib=False, monitor_class=None):
    """
    异步处理用户输入
    
    Args:
        server: MinecraftServer 实例
        monitor: 当前的监控器实例
        extra_jvm_args: JVM 参数列表
        has_matplotlib: 是否安装了 matplotlib
        monitor_class: 监控器类（用于动态创建监控器）
    """
    from yasl.utils import get_timestamp
    
    print("\n输入命令 (输入 'stop' 停止服务器):")

    while server.running and server.process and server.process.poll() is None:
        try:
            # 异步读取用户输入
            loop = asyncio.get_event_loop()
            user_input = await loop.run_in_executor(None, lambda: input("> ").strip())

            if not user_input:
                continue

            command = user_input.lower()

            # 处理特殊命令
            if command == "stop":
                print("正在停止服务器...")
                break

            elif command == "mem_chk":
                if not _HAS_PSUTIL:
                    print("psutil 未安装")
                else:
                    result = await get_process_info_async(server.process, "memory")
                    print(result)
                continue

            elif command == "usg_chk":
                if not _HAS_PSUTIL:
                    print("psutil 未安装")
                else:
                    result = await get_process_info_async(server.process, "cpu")
                    print(result)
                continue

            elif command == "monitor":
                if not has_matplotlib:
                    print("matplotlib 未安装，无法启动监控")
                elif monitor_class is None:
                    print("监控器类未提供")
                elif monitor:
                    if monitor.running:
                        monitor.stop()
                        print("监控已停止")
                    else:
                        monitor.start()
                        print("监控已启动")
                elif server.process:
                    try:
                        monitor = monitor_class(server.process, refresh_interval=0.05)
                        monitor.start()
                    except Exception as e:
                        print(f"监控器启动失败: {e}")
                continue

            elif command in ["extensions", "exts"]:
                if server.extension_manager:
                    exts = server.extension_manager.list_extensions()
                    print(f"已加载扩展 ({len(exts)}):")
                    for ext in exts:
                        info = server.extension_manager.get_extension_info(ext)
                        if info:
                            status = info.get("status", "unknown")
                            print(f"  - {ext} (状态: {status})")
                else:
                    print("扩展未启用")
                continue

            elif command.startswith("ext_reload "):
                if server.extension_manager:
                    ext_name = command[11:].strip()
                    if ext_name in server.extension_manager.list_extensions():
                        try:
                            await server.extension_manager.reload_extension_async(
                                ext_name
                            )
                            print(f"扩展 '{ext_name}' 已重新加载")
                        except Exception as e:
                            print(f"重新加载扩展失败: {e}")
                    else:
                        print(f"扩展 '{ext_name}' 不存在")
                else:
                    print("扩展未启用")
                continue

            elif command == "jvm_info":
                print("当前 JVM 参数:")
                for i, arg in enumerate(extra_jvm_args, 1):
                    print(f"  {i:2}. {arg}")
                continue

            elif command == "sys_info":
                if not _HAS_PSUTIL:
                    print("psutil 未安装")
                else:
                    cpu, mem = await get_system_info_async()
                    if cpu is not None and mem is not None:
                        print("系统信息:")
                        print(f"  CPU 使用率: {cpu}%")
                        print(
                            f"  内存使用: {mem.percent}% ({mem.used/(1024**3):.1f}GB / {mem.total/(1024**3):.1f}GB)"
                        )
                continue

            elif command == "help":
                print(_get_help_text())
                continue

            # 发送命令到服务器
            await server.send_command_async(user_input)

        except (KeyboardInterrupt, EOFError):
            print("\n检测到中断信号")
            break
        except Exception as e:
            print(f"命令执行错误: {e}")
    
    return monitor


def _get_help_text():
    """获取帮助文本"""
    return """
可用命令:
  stop       - 停止服务器
  mem_chk    - 查看内存使用
  usg_chk    - 查看CPU使用
  monitor    - 启动/停止监控图表
  extensions - 查看已加载扩展
  ext_reload <name> - 重新加载扩展
  jvm_info   - 查看JVM参数
  sys_info   - 查看系统状态
  help       - 显示此帮助
"""


def get_help_text():
    """获取帮助文本（公共接口）"""
    return _get_help_text()


async def get_java_version_async():
    """异步检测 Java 版本"""
    import re
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                ["java", "-version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
            ),
        )

        version_output = result.stderr if result.stderr else result.stdout
        if not version_output:
            return None, None, None

        patterns = [
            r'version\s+"(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:_(\d+))?(?:\.(\d+))?',
            r"(\d+)\.(\d+)\.(\d+)_(\d+)",
            r"(\d+)\.(\d+)\.(\d+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, version_output)
            if match:
                groups = match.groups()
                major = int(groups[0]) if groups[0] else 0
                minor = int(groups[1]) if len(groups) > 1 and groups[1] else 0
                update = int(groups[2]) if len(groups) > 2 and groups[2] else 0
                return major, minor, update

        simple_match = re.search(r'java version\s+"?(\d+)', version_output, re.IGNORECASE)
        if simple_match:
            return int(simple_match.group(1)), 0, 0

        return None, None, None

    except Exception as e:
        print(f"Java 版本检测失败: {e}")
        return None, None, None


# 导出模块接口
__all__ = [
    'parse_args',
    'handle_user_input',
    'get_process_info_async',
    'get_system_info_async',
    'get_help_text',
    'get_java_version_async',
    '_HAS_PSUTIL',
]