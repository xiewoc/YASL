"""YASL 启动入口 — 委托 LifeCycle 管理完整生命周期。"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from yasl.life_cycle import LifeCycle


args = []

args.extend(["-Xms10G", "-Xmx10G", "-Xss1M"])

args.extend([
    "-XX:+UnlockExperimentalVMOptions",
    "-XX:+UseZGC",
    "-XX:+ZGenerational",
    "-XX:+AlwaysPreTouch",
    "-XX:+ExplicitGCInvokesConcurrent",
    "-XX:+PerfDisableSharedMem",
    "-XX:SoftMaxHeapSize=8G",          # 新增：软上限，让 GC 更积极
])

args.extend(["-XX:MaxMetaspaceSize=2G"])

args.extend([
    "-Djava.awt.headless=true",
    "-Dforge.disableVersionCheck=true",
])
args.extend([
    "-Xlog:gc*=info:file=logs/gc.log:time,level,tags:filecount=5,filesize=100M"
])


async def _main(args) -> None:
    await LifeCycle().run(args)


if __name__ == "__main__":
    import asyncio

    try:
        asyncio.run(_main(args))
    except KeyboardInterrupt:
        print("\n程序被中断")