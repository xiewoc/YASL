"""示例扩展 — 监听玩家事件并在控制台输出。"""
from yasl.event_bus import EventType
from yasl.extension_loader import ExtensionBase
from yasl.logging import ExtensionLogger

_log = ExtensionLogger("example")


class ExampleExtension(ExtensionBase):
    name = "example"
    version = "1.0.0"

    async def on_enable(self) -> None:
        self.subscribe(EventType.PLAYER_JOIN, self._on_join)
        self.subscribe(EventType.PLAYER_LEAVE, self._on_leave)
        _log.info("扩展已启用")

    async def on_disable(self) -> None:
        self.unsubscribe(EventType.PLAYER_JOIN, self._on_join)
        self.unsubscribe(EventType.PLAYER_LEAVE, self._on_leave)
        _log.info("扩展已禁用")

    def _on_join(self, player_name: str = "?", **kwargs) -> None:
        _log.info(f"{player_name} 加入了游戏")

    def _on_leave(self, player_name: str = "?", **kwargs) -> None:
        _log.info(f"{player_name} 离开了游戏")
