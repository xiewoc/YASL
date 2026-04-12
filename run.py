# run.py
"""
Minecraft 服务器启动器入口文件
"""
import asyncio
import os
import signal
import sys

# 在导入其他模块之前设置路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from yasl.main import MinecraftServer
from yasl.utils import get_timestamp, ensure_dir


# 全局退出状态
_shutdown_requested = False
_shutdown_in_progress = False
_shutdown_event: asyncio.Event | None = None
_server_instance: MinecraftServer | None = None
_monitor_instance = None


def _signal_handler(signum, frame):
    """统一的信号处理器"""
    global _shutdown_requested
    
    if _shutdown_requested:
        # 第二次 Ctrl+C，强制退出
        print("\n[警告] 强制退出中...")
        sys.exit(130)
    
    _shutdown_requested = True
    print(f"\n[{get_timestamp()}] 收到退出信号 (Ctrl+C)，正在优雅关闭...")
    
    # 设置退出事件
    if _shutdown_event:
        _shutdown_event.set()


def _setup_signal_handlers():
    """设置信号处理器"""
    signal.signal(signal.SIGINT, _signal_handler)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, _signal_handler)


async def graceful_shutdown(server, monitor=None, timeout=30):
    """
    优雅关闭服务器
    
    Args:
        server: MinecraftServer 实例
        monitor: 监控器实例（可选）
        timeout: 强制关闭超时时间（秒）
    """
    global _shutdown_in_progress
    
    if _shutdown_in_progress:
        return  # 防止重复调用
    
    _shutdown_in_progress = True
    start_time_str = get_timestamp()
    
    print("\n" + "=" * 50)
    print(" 开始优雅关闭流程")
    print("=" * 50)
    
    steps = [
        ("停止监控器", lambda: _stop_monitor(monitor)),
        ("停止 Broken Pipe 监控", lambda: _stop_broken_pipe_monitor(server)),
        ("保存玩家数据", lambda: _save_playtime(server)),
        ("停止扩展系统", lambda: _stop_extensions(server)),
        ("停止 API 服务", lambda: _stop_api(server)),
        ("发送 stop 命令", lambda: _send_stop_command(server)),
        ("等待服务器进程结束", lambda: _wait_server_stop(server, timeout)),
    ]
    
    for step_name, step_func in steps:
        try:
            print(f"  → {step_name}...", end=" ", flush=True)
            result = await step_func()
            if result:
                print(f"✓")
            else:
                print(f"跳过")
        except asyncio.TimeoutError:
            print(f"超时!")
            print(f"  → 强制终止进程...")
            if server.process:
                server.process.terminate()
            break
        except Exception as e:
            print(f"错误: {e}")
    
    print("=" * 50)
    print(f" 关闭完成")
    print("=" * 50 + "\n")


async def _stop_monitor(monitor):
    """停止监控器"""
    if monitor and hasattr(monitor, 'running') and monitor.running:
        monitor.stop()
        return True
    return False


async def _stop_broken_pipe_monitor(server):
    """停止 Broken Pipe 监控"""
    if hasattr(server, 'stop_broken_pipe_monitor'):
        await server.stop_broken_pipe_monitor()
        return True
    return False


async def _save_playtime(server):
    """保存玩家游戏时间"""
    if server.playtime_manager:
        server.playtime_manager.shutdown()
        return True
    return False


async def _stop_extensions(server):
    """停止扩展系统"""
    if server.extension_manager:
        await server._stop_extensions()
        return True
    return False


async def _stop_api(server):
    """停止 API 服务"""
    if server.api_enabled:
        try:
            await server.stop_api()
            return True
        except Exception:
            pass
    return False


async def _send_stop_command(server):
    """发送 stop 命令"""
    if server.running and server.process:
        try:
            await server.send_command_async("stop", timeout=2.0)
            return True
        except Exception:
            pass
    return False


async def _wait_server_stop(server, timeout):
    """等待服务器进程结束"""
    if not server.process:
        return False
    
    loop = asyncio.get_event_loop()
    try:
        await asyncio.wait_for(
            loop.run_in_executor(None, lambda: server.process.wait()),
            timeout=timeout
        )
        server.running = False
        return True
    except asyncio.TimeoutError:
        raise


def get_optimized_jvm_args(java_major=None):
    """
    获取优化的 JVM 参数
    
    Args:
        java_major: Java 主版本号
    
    Returns:
        JVM 参数列表
    """
    try:
        import psutil
        
        cpu_count = psutil.cpu_count(logical=True) or 4
        memory = psutil.virtual_memory()
        total_memory_gb = memory.total / (1024**3)
        
        print(f"Java 专用优化 - 内存: {total_memory_gb:.1f}GB, Java版本: {java_major or '未知'}")
        
        args = []
        
        # 1. 基础内存设置
        xms_gb = 5
        xmx_gb = 6 if total_memory_gb >= 16 else 6
        
        args.extend([f"-Xms{xms_gb}G", f"-Xmx{xmx_gb}G", "-Xss1M"])
        
        # 2. GC选择
        args.extend(["-XX:+UseG1GC", "-server"])
        
        # 3. 解锁实验性选项
        args.extend(["-XX:+UnlockExperimentalVMOptions"])
        
        # 4. G1GC实验性参数
        args.extend([
            "-XX:G1NewSizePercent=40", "-XX:G1MaxNewSizePercent=70",
            "-XX:G1HeapRegionSize=4M", "-XX:G1ReservePercent=15",
            "-XX:InitiatingHeapOccupancyPercent=40",
            "-XX:G1MixedGCCountTarget=16", "-XX:G1HeapWastePercent=10",
        ])
        
        # 5. 标准G1GC参数
        args.extend(["-XX:+ParallelRefProcEnabled", "-XX:MaxGCPauseMillis=100", "-XX:+AlwaysPreTouch"])
        
        # 6. 内存和性能优化
        args.extend([
            "-XX:MetaspaceSize=256M", "-XX:MaxMetaspaceSize=512M",
            "-XX:+UseCompressedOops", "-XX:+UseCompressedClassPointers",
            "-XX:+UseStringDeduplication", "-XX:StringDeduplicationAgeThreshold=3",
        ])
        
        # 7. 系统属性
        args.extend([
            "-Dfile.encoding=UTF-8", "-Djava.awt.headless=true",
            "-Dsun.rmi.dgc.server.gcInterval=2147483646",
            "-Dsun.rmi.dgc.client.gcInterval=2147483646",
        ])
        
        # 8. 诊断
        ensure_dir("logs")
        args.extend([
            "-XX:+HeapDumpOnOutOfMemoryError",
            "-XX:HeapDumpPath=logs/heapdump.hprof",
            "-XX:ErrorFile=logs/hs_err_pid%p.log",
        ])
        
        # 9. GC日志
        if java_major and java_major >= 9:
            args.extend(["-Xlog:gc:file=logs/gc.log:time,level:filecount=3,filesize=10M"])
        else:
            args.extend(["-Xloggc:logs/gc.log", "-XX:+PrintGCDetails", "-XX:+PrintGCDateStamps", "-XX:+PrintGCTimeStamps"])
        
        return args
        
    except ImportError:
        print("psutil 未安装，使用默认 JVM 参数")
        return ["-Xms5G", "-Xmx6G", "-XX:+UseG1GC"]
    except Exception as e:
        print(f"获取 JVM 参数失败: {e}")
        return ["-Xms5G", "-Xmx6G", "-XX:+UseG1GC"]


async def main():
    global _shutdown_event, _server_instance, _monitor_instance
    
    # 从 yasl 包导入模块
    from yasl.commands import parse_args, handle_user_input, get_java_version_async
    from yasl.monitor import RealTimeMonitor, _check_dependencies, _HAS_MATPLOTLIB, _HAS_PSUTIL
    
    # 设置信号处理器
    _setup_signal_handlers()
    
    # 创建退出事件
    _shutdown_event = asyncio.Event()
    
    # 检查依赖
    has_deps = _check_dependencies()

    # --- 主逻辑 ---
    args = parse_args()

    print("=" * 60)
    print("Minecraft 服务器启动器")
    print("=" * 60)

    # 创建服务器实例
    server = MinecraftServer(
        forge_version="",
        log_level=args.log_level,
        use_colors=not args.no_colors,
        filter_sources=["mixin", "ModernFix", "Jade", "terrablender"],
        enable_extensions=not args.no_extensions,
        enable_api=True,
        api_host="0.0.0.0",
        api_port=8000,
    )

    # 检测 Java 版本
    java_major, java_minor, _ = await get_java_version_async()
    
    extra_jvm_args = get_optimized_jvm_args(java_major)

    # 用户指定的内存设置
    if args.jvm_memory_min:
        for i, arg in enumerate(extra_jvm_args):
            if arg.startswith("-Xms"):
                extra_jvm_args[i] = f"-Xms{args.jvm_memory_min}G"
                break

    if args.jvm_memory_max:
        for i, arg in enumerate(extra_jvm_args):
            if arg.startswith("-Xmx"):
                extra_jvm_args[i] = f"-Xmx{args.jvm_memory_max}G"
                break

    # 确保日志目录存在
    ensure_dir("logs")

    # 初始化监控器
    monitor = None
    if args.monitor:
        if not _HAS_MATPLOTLIB:
            print("  matplotlib 未安装，无法启动监控")
        elif not _HAS_PSUTIL:
            print("  psutil 未安装，无法启动监控")
        else:
            print(f"\n监控配置: 刷新率 {args.refresh_rate*1000:.0f}ms")

    # 注册全局实例
    _server_instance = server
    
    try:
        print("\n[3/3] 启动服务器...")
        print("-" * 60)

        await server.start(extra_args=extra_jvm_args, show_all_logs=args.show_all)

        # 启动监控器
        if args.monitor and _HAS_MATPLOTLIB and _HAS_PSUTIL and server.process:
            try:
                monitor = RealTimeMonitor(server.process, refresh_interval=args.refresh_rate)
                monitor.start()
                _monitor_instance = monitor
            except Exception as e:
                print(f"监控器启动失败: {e}")

        # 启动 Broken Pipe 监控（每10秒检测一次）
        if server.process:
            await server.start_broken_pipe_monitor(interval=10.0)

        # 显示欢迎信息
        current_time = get_timestamp()
        print(f"\n{'='*60}")
        print(" Minecraft 服务器已启动! ")
        print(f"  时间: {current_time}")
        print(f"  PID: {server.process.pid if server.process else 'N/A'}")
        print(f"{'='*60}")
        print("\n输入 'help' 查看可用命令")
        print("输入 'stop' 停止服务器")
        print("按 Ctrl+C 优雅退出")
        print("-" * 60)

        # 创建用户输入任务和退出事件等待任务
        input_task = asyncio.create_task(
            handle_user_input(
                server, monitor, extra_jvm_args, 
                has_matplotlib=_HAS_MATPLOTLIB, 
                monitor_class=RealTimeMonitor
            )
        )
        
        shutdown_wait_task = asyncio.create_task(_shutdown_event.wait())
        
        # 等待任一任务完成
        done, pending = await asyncio.wait(
            [input_task, shutdown_wait_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        # 取消未完成的任务
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        # 如果是因为退出事件触发，执行优雅关闭
        if _shutdown_requested or shutdown_wait_task in done:
            await graceful_shutdown(server, monitor)

    except KeyboardInterrupt:
        # 信号处理器已经设置了 _shutdown_requested，直接执行优雅关闭
        await graceful_shutdown(server, monitor)
    except Exception as e:
        print(f"\n[{get_timestamp()}] 启动错误: {e}")
        await graceful_shutdown(server, monitor)

    finally:
        print("\n服务器已停止")
        print("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n程序被用户中断")
    except Exception as e:
        print(f"\n程序异常: {e}")
        import traceback
        traceback.print_exc()