"""
YASL 扩展模块

扩展开发指南:
=============

1. 扩展生命周期:
   - init(): 初始化函数，在模块加载后调用
   - main(): 主函数，作为异步任务启动（可选，用于持续运行的任务）
   - cleanup(): 清理函数，在卸载扩展时调用

2. 可用注入变量（由扩展管理器自动注入）:
   - bus: 事件总线实例
   - data_dir: 扩展数据目录路径 (Path对象)
   - log: 扩展专用日志函数 log(message, level)
   - datetime: datetime 模块
   - asyncio: asyncio 模块
   - time: time 模块
   - os: os 模块
   - Path: pathlib.Path 类

3. 事件处理:
   使用 @event_handler 装饰器注册事件处理器:

   from yasl.extension_manager import event_handler

   @event_handler('player_chat')
   async def on_player_chat(event_message):
       print(f"玩家聊天: {event_message.message_contained}")

4. 扩展模板:

   ```
   '''
   扩展名称

   功能:
   - 功能描述

   生命周期:
   - init(): 初始化
   - main(): 主循环（可选）
   - cleanup(): 清理
   '''

   import logging

   logger = logging.getLogger(__name__)

   def init():
       '''初始化扩展'''
       logger.info("扩展初始化完成")

   async def main():
       '''主函数 - 持续运行'''
       while True:
           # 执行任务
           await asyncio.sleep(60)

   def cleanup():
       '''清理函数'''
       logger.info("扩展已清理")
   ```

5. 注意事项:
   - 使用 logging.getLogger(__name__) 获取日志器
   - 使用 data_dir 存储扩展数据
   - 异步任务放在 main() 函数中
   - 清理资源在 cleanup() 函数中
"""

from yasl.extension_manager import (
    ExtensionManager,
    event_handler,
    get_extension_manager,
    reset_extension_manager,
)

__all__ = [
    "ExtensionManager",
    "event_handler",
    "get_extension_manager",
    "reset_extension_manager",
]