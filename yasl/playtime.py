"""
玩家游戏时间管理模块
用于统计 Minecraft 服务器玩家的游玩时间
支持从日志消息或事件总线处理玩家加入/离开事件
"""

import os
import threading
import json
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class PlayTimeManager:
    """玩家游戏时间管理器 - 简化版，只记录总累计时间"""
    
    def __init__(self, data_file: str = "player_playtime.json"):
        self.data_file = data_file
        # 玩家数据: {player_name: {"total_seconds": int, "first_join": str}}
        self._sessions: Dict[str, dict] = {}
        # 在线玩家: {player_name: login_time_iso}
        self._online_players: Dict[str, str] = {}
        self._lock = threading.RLock()
        self._initialized = False
        self._last_save_time = 0
        self._save_interval = 60  # 最小保存间隔（秒）
        self._auto_save_thread: Optional[threading.Thread] = None
        self._stop_auto_save = threading.Event()
        
        # 加载数据
        self._load()
        self._initialized = True
        
        # 启动自动保存线程
        self._start_auto_save()
        
        logger.info(f"PlayTimeManager initialized with {len(self._sessions)} players")
    
    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._initialized
    
    def _start_auto_save(self):
        """启动自动保存线程，定期保存在线玩家的累计时间"""
        def auto_save_loop():
            while not self._stop_auto_save.is_set():
                # 每30秒保存一次在线玩家的当前会话时间
                self._stop_auto_save.wait(30)
                if not self._stop_auto_save.is_set():
                    self._save_online_sessions()
        
        self._auto_save_thread = threading.Thread(target=auto_save_loop, daemon=True, name="PlayTimeAutoSave")
        self._auto_save_thread.start()
        logger.info("Auto-save thread started (interval: 30s)")
    
    def _save_online_sessions(self):
        """保存在线玩家的当前会话时间到总累计时间（防止数据丢失）"""
        with self._lock:
            if not self._online_players:
                return
            
            now = datetime.now()
            for player_name, login_time in list(self._online_players.items()):
                try:
                    login_dt = datetime.fromisoformat(login_time)
                    session_seconds = int((now - login_dt).total_seconds())
                    
                    # 确保玩家数据存在
                    if player_name not in self._sessions:
                        self._sessions[player_name] = {
                            "total_seconds": 0,
                            "first_join": login_time
                        }
                    
                    # 累加到总时间
                    self._sessions[player_name]["total_seconds"] += session_seconds
                    
                    # 更新登录时间为当前时间（避免重复计算）
                    self._online_players[player_name] = now.isoformat()
                    
                    logger.debug(f"Auto-saved session for {player_name}: +{session_seconds}s")
                except Exception as e:
                    logger.error(f"Error auto-saving session for {player_name}: {e}")
            
            # 保存到文件
            self._save_to_file()
    
    def _load(self):
        """加载数据"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, "r", encoding="utf-8") as f:
                    self._sessions = json.load(f)
                    logger.info(f"Loaded playtime data for {len(self._sessions)} players")
        except Exception as e:
            logger.error(f"Error loading playtime data: {e}")
            self._sessions = {}
    
    def _save_to_file(self):
        """保存数据到文件"""
        try:
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(self._sessions, f, ensure_ascii=False, indent=2)
            self._last_save_time = datetime.now().timestamp()
        except Exception as e:
            logger.error(f"Error saving playtime data: {e}")
    
    def save(self, force: bool = False) -> None:
        """保存数据（带节流）"""
        current_time = datetime.now().timestamp()
        
        # 除非强制保存，否则限制保存频率
        if not force and current_time - self._last_save_time < self._save_interval:
            return
        
        with self._lock:
            self._save_to_file()
    
    def process_event(self, event_data: Dict[str, Any]) -> Optional[Dict]:
        """
        处理事件数据（推荐方式）
        接收来自事件总线的标准化事件数据
        """
        extra = event_data.get("extra", {})
        msg_type = extra.get("type", "")
        
        if msg_type == "player_join":
            player_name = extra.get("player_name", "")
            if player_name:
                return self._player_join(player_name)
        
        elif msg_type == "player_leave":
            player_name = extra.get("player_name", "")
            if player_name:
                return self._player_leave(player_name)
        
        return None
    
    def process_log_message(self, message: str, extra_info: Optional[Dict] = None) -> Optional[Dict]:
        """
        处理日志消息（向后兼容）
        如果提供了 extra_info，优先使用其中的信息
        """
        # 如果有额外信息，优先使用
        if extra_info:
            return self.process_event({
                "extra": extra_info,
                "message": message
            })
        
        # 解析消息（简化版本）
        msg_type = ""
        player_name = ""
        
        if " joined the game" in message:
            msg_type = "player_join"
            # 提取玩家名
            parts = message.split(" joined the game")
            if parts:
                player_name = parts[0].split()[-1]
        elif " left the game" in message:
            msg_type = "player_leave"
            parts = message.split(" left the game")
            if parts:
                player_name = parts[0].split()[-1]
        elif " lost connection:" in message:
            msg_type = "player_leave"
            parts = message.split(" lost connection:")
            if parts:
                player_name = parts[0].split()[-1]
        
        if msg_type and player_name:
            if msg_type == "player_join":
                return self._player_join(player_name)
            else:
                return self._player_leave(player_name)
        
        return None
    
    # 保持向后兼容的别名
    process_log = process_log_message
    
    def _player_join(self, player_name: str) -> Optional[Dict]:
        """玩家加入处理"""
        with self._lock:
            login_time = datetime.now().isoformat()
            self._online_players[player_name] = login_time
            
            # 初始化玩家数据
            if player_name not in self._sessions:
                self._sessions[player_name] = {
                    "total_seconds": 0,
                    "first_join": login_time
                }
            
            logger.debug(f"Player {player_name} joined")
            return {"event": "join", "player": player_name, "time": login_time}
    
    def _player_leave(self, player_name: str) -> Optional[Dict]:
        """玩家离开处理"""
        with self._lock:
            if player_name not in self._online_players:
                return None
            
            login_time = self._online_players.pop(player_name)
            
            try:
                login_dt = datetime.fromisoformat(login_time)
                logout_dt = datetime.now()
                session_seconds = int((logout_dt - login_dt).total_seconds())
                
                if player_name not in self._sessions:
                    self._sessions[player_name] = {"total_seconds": 0, "first_join": login_time}
                
                # 累加到总时间
                self._sessions[player_name]["total_seconds"] += session_seconds
                
                # 保存数据
                self.save(force=True)
                
                logger.debug(f"Player {player_name} played for {session_seconds} seconds")
                return {
                    "event": "leave", 
                    "player": player_name, 
                    "duration": session_seconds,
                    "total": self._sessions[player_name]["total_seconds"]
                }
            except Exception as e:
                logger.error(f"Error calculating playtime for {player_name}: {e}")
                return None
    
    def get_player_summary(self, player_name: str) -> Optional[Dict]:
        """获取玩家游戏时间摘要"""
        with self._lock:
            if player_name not in self._sessions:
                return None
            
            data = self._sessions[player_name]
            total_seconds = data.get("total_seconds", 0)
            
            # 当前在线时间
            is_online = player_name in self._online_players
            if is_online:
                try:
                    login_dt = datetime.fromisoformat(self._online_players[player_name])
                    total_seconds += int((datetime.now() - login_dt).total_seconds())
                except Exception:
                    pass
            
            # 格式化时间
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            
            return {
                "player": player_name,
                "total_seconds": total_seconds,
                "total_hours": round(total_seconds / 3600, 2),
                "formatted": f"{hours}小时{minutes}分钟{seconds}秒",
                "is_online": is_online,
                "login_time": self._online_players.get(player_name),
                "first_join": data.get("first_join")
            }
    
    def get_all_players(self, sort_by: str = "total_seconds", reverse: bool = True) -> List[Dict]:
        """获取所有玩家数据"""
        with self._lock:
            result = []
            for player_name in self._sessions:
                summary = self._build_summary(player_name, self._sessions[player_name])
                if summary:
                    result.append(summary)
            
            # 排序
            if sort_by in ["total_seconds", "total_hours"]:
                result.sort(key=lambda x: x.get(sort_by, 0), reverse=reverse)
            
            return result
    
    def _build_summary(self, player_name: str, data: dict) -> Optional[Dict]:
        """构建玩家摘要（内部方法，不加锁）"""
        try:
            total_seconds = data.get("total_seconds", 0)
            
            is_online = player_name in self._online_players
            if is_online:
                try:
                    login_dt = datetime.fromisoformat(self._online_players[player_name])
                    total_seconds += int((datetime.now() - login_dt).total_seconds())
                except Exception:
                    pass
            
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            
            return {
                "player": player_name,
                "total_seconds": total_seconds,
                "total_hours": round(total_seconds / 3600, 2),
                "formatted": f"{hours}小时{minutes}分钟{seconds}秒",
                "is_online": is_online,
                "login_time": self._online_players.get(player_name),
                "first_join": data.get("first_join")
            }
        except Exception:
            return None
    
    def get_online_players(self) -> List[Dict]:
        """获取当前在线玩家"""
        with self._lock:
            result = []
            for player_name in list(self._online_players.keys()):
                if player_name in self._sessions:
                    summary = self._build_summary(player_name, self._sessions[player_name])
                    if summary:
                        result.append(summary)
            return result
    
    def search_players(self, keyword: str, limit: int = 20) -> List[Dict]:
        """搜索玩家"""
        with self._lock:
            keyword_lower = keyword.lower()
            result = []
            for player_name in self._sessions:
                if keyword_lower in player_name.lower():
                    summary = self._build_summary(player_name, self._sessions[player_name])
                    if summary:
                        result.append(summary)
                        if len(result) >= limit:
                            break
            return result
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        with self._lock:
            total_players = len(self._sessions)
            online_count = len(self._online_players)
            total_playtime = sum(
                s.get("total_seconds", 0) for s in self._sessions.values()
            )
            
            return {
                "total_players": total_players,
                "online_players": online_count,
                "total_playtime_seconds": total_playtime,
                "total_playtime_hours": round(total_playtime / 3600, 2)
            }
    
    def reset_player(self, player_name: str) -> bool:
        """重置玩家数据"""
        with self._lock:
            if player_name in self._sessions:
                del self._sessions[player_name]
                if player_name in self._online_players:
                    del self._online_players[player_name]
                self.save(force=True)
                return True
            return False
    
    def shutdown(self) -> None:
        """关闭时保存数据"""
        logger.info("PlayTimeManager shutting down...")
        
        # 先保存在线玩家的会话时间（在停止线程之前）
        with self._lock:
            if self._online_players:
                logger.info(f"Saving {len(self._online_players)} online player(s) session time...")
                now = datetime.now()
                for player_name, login_time in list(self._online_players.items()):
                    try:
                        login_dt = datetime.fromisoformat(login_time)
                        session_seconds = int((now - login_dt).total_seconds())
                        
                        # 确保玩家数据存在
                        if player_name not in self._sessions:
                            self._sessions[player_name] = {
                                "total_seconds": 0,
                                "first_join": login_time
                            }
                        
                        # 累加到总时间
                        self._sessions[player_name]["total_seconds"] += session_seconds
                        logger.info(f"Saved session for {player_name}: +{session_seconds}s, total: {self._sessions[player_name]['total_seconds']}s")
                    except Exception as e:
                        logger.error(f"Error saving session for {player_name}: {e}")
                
                # 清空在线玩家列表
                self._online_players.clear()
        
        # 停止自动保存线程
        self._stop_auto_save.set()
        if self._auto_save_thread and self._auto_save_thread.is_alive():
            self._auto_save_thread.join(timeout=2.0)
        
        # 强制保存数据到文件
        self._save_to_file()
        logger.info(f"PlayTimeManager shutdown complete, saved {len(self._sessions)} player(s) data")


# 全局实例（供外部访问）
_playtime_manager: Optional[PlayTimeManager] = None


def get_playtime_manager() -> Optional[PlayTimeManager]:
    """获取全局游戏时间管理器实例"""
    return _playtime_manager


def create_playtime_manager(data_file: str = "player_playtime.json") -> PlayTimeManager:
    """创建并返回全局游戏时间管理器实例"""
    global _playtime_manager
    _playtime_manager = PlayTimeManager(data_file)
    return _playtime_manager