"""游玩时间统计扩展 — 记录玩家本次和累计游玩时间。"""
import json
import threading
import time
from datetime import timedelta
from pathlib import Path

from yasl.event_bus import EventType
from yasl.extension_loader import ExtensionBase


class PlaytimeExtension(ExtensionBase):
    name = "playtime"
    version = "1.0.0"

    _data_file: Path | None = None
    _session_start: dict[str, float] = {}   # player → 本次上线时间戳
    _cumulative: dict[str, float] = {}      # player → 累计秒数
    _lock = threading.Lock()

    # ----------------------------------------------------------------
    async def on_enable(self) -> None:
        self._data_file = Path(__file__).parent / "playtime.json"
        self._load()

        self.subscribe(EventType.PLAYER_JOIN, self._on_join)
        self.subscribe(EventType.PLAYER_LEAVE, self._on_leave)
        print("  [Playtime] 已启用")

    async def on_disable(self) -> None:
        self.unsubscribe(EventType.PLAYER_JOIN, self._on_join)
        self.unsubscribe(EventType.PLAYER_LEAVE, self._on_leave)

        # 离线时保存所有在线玩家的段内时间
        for player in list(self._session_start.keys()):
            self._finalize(player)
        self._save()
        print("  [Playtime] 已禁用")

    # ----------------------------------------------------------------
    # 事件回调
    # ----------------------------------------------------------------
    def _on_join(self, player_name: str = "?", **kwargs) -> None:
        with self._lock:
            self._session_start[player_name] = time.monotonic()
        print(f"  [Playtime] {player_name} 上线 (累计 {self._fmt(player_name)})")

    def _on_leave(self, player_name: str = "?", **kwargs) -> None:
        self._finalize(player_name)
        self._save()
        print(f"  [Playtime] {player_name} 下线 (累计 {self._fmt(player_name)})")

    def _finalize(self, player: str) -> None:
        with self._lock:
            start = self._session_start.pop(player, None)
        if start is None:
            return
        elapsed = time.monotonic() - start
        with self._lock:
            self._cumulative[player] = self._cumulative.get(player, 0.0) + elapsed

    # ----------------------------------------------------------------
    # 持久化
    # ----------------------------------------------------------------
    def _load(self) -> None:
        if self._data_file and self._data_file.exists():
            try:
                with open(self._data_file, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    self._cumulative = {k: float(v) for k, v in raw.items()}
            except Exception:
                pass

    def _save(self) -> None:
        if not self._data_file:
            return
        try:
            with open(self._data_file, "w", encoding="utf-8") as f:
                json.dump(self._cumulative, f, indent=2)
        except Exception:
            pass

    # ----------------------------------------------------------------
    # 查询
    # ----------------------------------------------------------------
    def _fmt(self, player: str) -> str:
        secs = self._cumulative.get(player, 0.0)
        return str(timedelta(seconds=int(secs)))

    def get_cumulative(self, player: str) -> float:
        """返回玩家累计秒数。"""
        return self._cumulative.get(player, 0.0)

    def get_session_elapsed(self, player: str) -> float:
        """返回本次在线秒数（在线中），不在线返回 0。"""
        start = self._session_start.get(player)
        if start is None:
            return 0.0
        return time.monotonic() - start

    def get_all_players(self) -> dict[str, float]:
        """返回所有有记录的玩家及其累计秒数。"""
        return dict(self._cumulative)