"""YASL 启动入口 — 委托 LifeCycle 管理完整生命周期。"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from yasl.life_cycle import LifeCycle


args = []

# 1. 堆内存配置
args.extend(["-Xms20G", "-Xmx20G", "-Xss1M"])

# 2. GC 选择 与 解锁实验性选项 (必须放在所有 G1 实验性参数之前!)
args.extend(["-XX:+UseG1GC", "-server"])
args.extend(["-XX:+UnlockExperimentalVMOptions"])

# 3. 所有 G1GC 参数 (包含标准参数和实验性参数，此时解锁已生效)
args.extend([
    "-XX:+ParallelRefProcEnabled",
    "-XX:MaxGCPauseMillis=500",      # 核心优化：放宽暂停目标
    "-XX:+AlwaysPreTouch",
    "-XX:+DisableExplicitGC",
    "-XX:InitiatingHeapOccupancyPercent=40",
    "-XX:+PerfDisableSharedMem",
    "-XX:MaxTenuringThreshold=15",
    "-XX:G1HeapRegionSize=32M",      # 新增：固定 Region 大小
    
    # === 以下为实验性参数 (此时 UnlockExperimentalVMOptions 已生效) ===
    "-XX:G1MaxNewSizePercent=70",    # 允许年轻代更大，减少 GC 频率
    "-XX:G1MixedGCLiveThresholdPercent=90",
    "-XX:G1RSetUpdatingPauseTimePercent=5",
])

# 4. Metaspace 配置
args.extend(["-XX:MetaspaceSize=1G", "-XX:MaxMetaspaceSize=2G"])

# 5. 系统属性
args.extend(["-Djava.awt.headless=true", "-Dforge.disableVersionCheck=true"])

# 6. GC 日志
args.extend(["-Xlog:gc*=info:file=logs/gc.log:time,level,tags:filecount=5,filesize=100M"])

# -XX:+UseStringDeduplication 已移除 (节省 CPU)


async def _main(args) -> None:
    await LifeCycle().run(args)


if __name__ == "__main__":
    import asyncio

    try:
        asyncio.run(_main(args))
    except KeyboardInterrupt:
        print("\n程序被中断")