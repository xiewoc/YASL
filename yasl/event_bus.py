"""事件总线 — 基于 SpecialPattern 的触发器与监听器。"""
from typing import Callable, Dict, List, Any, Optional
import inspect


# ---------------------------------------------------------------------------
# 事件类型常量 — 与 SpecialPattern.PATTERNS 一一对应
# ---------------------------------------------------------------------------
class EventType:
    """所有可监听的事件类型字符串常量。"""

    # ---- 服务器生命周期 ----
    STARTING        = "server.starting"        # Starting Minecraft server on ...
    STARTED         = "server.started"         # Done (启动完成)
    STOPPING        = "server.stopping"        # Stopping server
    SHUTTING_DOWN   = "server.shutting_down"   # shutting down
    PREPARING       = "server.preparing"       # Preparing spawn area
    CRASH           = "server.crash"           # crash

    # ---- 性能 ----
    CANT_KEEP_UP    = "server.cant_keep_up"    # Can't keep up

    # ---- 异常 / 错误 ----
    ERROR           = "server.error"           # error / exception
    FAIL            = "server.fail"            # fail
    SUCCESS         = "server.success"         # success (某些插件输出)

    # ---- 玩家事件 ----
    PLAYER_JOIN     = "player.join"            # joined the game
    PLAYER_LEAVE    = "player.leave"           # left / lost connection
    PLAYER_CHAT     = "player.chat"            # <player> message
    PLAYER_COMMAND  = "player.command"         # issued server command
    PLAYER_SAY      = "player.say"             # [Server: player]
    PLAYER_WHISPER  = "player.whisper"         # [sender -> receiver]


# ---------------------------------------------------------------------------
# SpecialPattern 的 type 字段 → EventType 映射
# ---------------------------------------------------------------------------
TYPE_TO_EVENT: Dict[str, str] = {
    # 服务器
    "starting":       EventType.STARTING,
    "done":           EventType.STARTED,
    "stopping":       EventType.STOPPING,
    "shutting_down":  EventType.SHUTTING_DOWN,
    "preparing":      EventType.PREPARING,
    "crash":          EventType.CRASH,
    # 性能
    "cant_keep_up":   EventType.CANT_KEEP_UP,
    # 异常
    "error":          EventType.ERROR,
    "exception":      EventType.ERROR,
    "fail":           EventType.FAIL,
    "success":        EventType.SUCCESS,
    # 玩家
    "player_join":    EventType.PLAYER_JOIN,
    "player_leave_lost": EventType.PLAYER_LEAVE,
    "player_leave_left": EventType.PLAYER_LEAVE,
    "player_chat":    EventType.PLAYER_CHAT,
    "player_command": EventType.PLAYER_COMMAND,
    "player_say":     EventType.PLAYER_SAY,
    "player_whisper": EventType.PLAYER_WHISPER,
}


# ---------------------------------------------------------------------------
# 事件总线
# ---------------------------------------------------------------------------
class EventBus:
    """全局事件总线（单例），支持基于事件类型的发布/订阅。"""

    __slots__ = ("_listeners",)
    _instance: Optional["EventBus"] = None
    _listeners: Dict[str, List[Callable]]

    def __new__(cls) -> "EventBus":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._listeners = {}
        return cls._instance

    # -- 注册 / 注销 ------------------------------------------------

    def subscribe(self, event_type: str, callback: Callable[..., Any]) -> None:
        """注册一个监听器。"""
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        if callback not in self._listeners[event_type]:
            self._listeners[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable[..., Any]) -> None:
        """注销一个监听器。"""
        if event_type in self._listeners:
            try:
                self._listeners[event_type].remove(callback)
            except ValueError:
                pass

    # -- 触发 ------------------------------------------------------

    def publish(self, event_type: str, **kwargs: Any) -> None:
        """触发事件，向所有注册的回调传递 **kwargs。"""
        callbacks = self._listeners.get(event_type, ())
        if not callbacks:
            return
        for cb in callbacks:
            try:
                sig = inspect.signature(cb)
                accepted = {k: v for k, v in kwargs.items() if k in sig.parameters}
                cb(**accepted)
            except Exception:
                pass


# 模块级便捷函数 — 直接操作全局单例
_bus = EventBus()

subscribe   = _bus.subscribe
unsubscribe = _bus.unsubscribe
publish     = _bus.publish