"""
聊天记录扩展

功能:
- 记录玩家聊天消息到 JSON 文件
- 支持事件总线集成
- 提供搜索和导出功能

生命周期:
- init(): 初始化日志文件
- cleanup(): 清理资源

事件处理:
- player_chat: 玩家聊天事件
- log: 日志事件（备用解析）
"""

import json
import re
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

# 扩展专用日志
logger = logging.getLogger(__name__)

# 聊天消息正则表达式
CHAT_PATTERN = re.compile(r"<([^>]+)>\s+(.+)$")

# 最大消息数量
MAX_MESSAGES = 1000


class ChatLogger:
    """聊天记录记录器"""

    def __init__(self, log_file: Path):
        """
        初始化聊天记录器

        Args:
            log_file: 日志文件路径
        """
        self.log_file = log_file
        self._ensure_log_file()

    def _ensure_log_file(self):
        """确保日志文件存在"""
        if not self.log_file.exists():
            self._save_data({"messages": []})

    def _load_data(self) -> Dict[str, List]:
        """加载日志数据"""
        try:
            if self.log_file.exists():
                with open(self.log_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"加载日志文件失败: {e}")

        return {"messages": []}

    def _save_data(self, data: Dict[str, List]):
        """保存日志数据"""
        try:
            with open(self.log_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存日志文件失败: {e}")

    def save_message(self, log_entry: Dict[str, Any]):
        """
        保存聊天消息

        Args:
            log_entry: 日志条目
        """
        data = self._load_data()

        if "messages" not in data:
            data["messages"] = []

        data["messages"].append(log_entry)

        # 限制消息数量
        if len(data["messages"]) > MAX_MESSAGES:
            data["messages"] = data["messages"][-MAX_MESSAGES:]

        self._save_data(data)

    def search(
        self,
        keyword: Optional[str] = None,
        player: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        搜索聊天记录

        Args:
            keyword: 关键词过滤
            player: 玩家名过滤
            limit: 返回数量限制

        Returns:
            匹配的消息列表
        """
        data = self._load_data()
        messages = data.get("messages", [])

        filtered = []
        for msg in messages:
            if player and msg.get("player") != player:
                continue
            if keyword and keyword.lower() not in msg.get("message", "").lower():
                continue
            filtered.append(msg)

        return filtered[-limit:]

    def export(self, format: str = "json", filename: Optional[str] = None) -> Tuple[bool, str]:
        """
        导出聊天记录

        Args:
            format: 导出格式 (json/txt)
            filename: 导出文件名

        Returns:
            (成功标志, 消息)
        """
        data = self._load_data()

        if format == "json":
            export_file = filename or "chat_export.json"
            with open(export_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True, f"导出到 {export_file}"

        elif format == "txt":
            export_file = filename or "chat_export.txt"
            with open(export_file, "w", encoding="utf-8") as f:
                f.write("=== Minecraft 聊天记录 ===\n\n")
                for msg in data.get("messages", []):
                    timestamp = msg.get("timestamp", "")
                    player = msg.get("player", "Unknown")
                    message = msg.get("message", "")

                    try:
                        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                        time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        time_str = timestamp

                    f.write(f"[{time_str}] <{player}> {message}\n")
            return True, f"导出到 {export_file}"

        return False, f"不支持的格式: {format}"


# ============ 扩展接口 ============

_logger_instance: Optional[ChatLogger] = None


def init():
    """初始化扩展"""
    global _logger_instance

    # 使用扩展管理器提供的 data_dir
    log_dir = data_dir if 'data_dir' in dir() else Path(".")

    log_file = Path(log_dir) / "chat_log.json"
    _logger_instance = ChatLogger(log_file)

    logger.info("聊天记录扩展初始化完成")
    logger.info(f"日志文件: {log_file}")


def cleanup():
    """清理函数"""
    global _logger_instance
    logger.info("聊天记录扩展已清理")
    _logger_instance = None


# ============ 事件处理器 ============

from yasl.extension_manager import event_handler


@event_handler("player_chat")
def on_player_chat_event(event_message):
    """处理玩家聊天事件"""
    if _logger_instance is None:
        return

    try:
        message_contained = event_message.message_contained
        player_name = message_contained.get("player_name", "")
        chat_content = message_contained.get("message", "")

        if not player_name or not chat_content:
            return

        log_entry = {
            "timestamp": message_contained.get("timestamp", datetime.now().isoformat()),
            "server_time": message_contained.get("server_time", ""),
            "player": player_name,
            "message": chat_content,
            "source": message_contained.get("source", "unknown"),
            "event_type": "player_chat",
        }

        _logger_instance.save_message(log_entry)
        _print_chat_message(log_entry)

    except Exception as e:
        logger.error(f"处理聊天事件出错: {e}")


@event_handler("log")
def on_log_message(event_message):
    """备用：从日志中检测聊天消息"""
    if _logger_instance is None:
        return

    try:
        message_contained = event_message.message_contained
        level = message_contained.get("level", "")
        source = message_contained.get("source", "")
        message = message_contained.get("message", "")
        extra = message_contained.get("extra", {})

        # 检查是否是玩家聊天消息（log.py 已经解析好了）
        msg_type = extra.get("type", "")
        if msg_type == "player_chat":
            player_name = extra.get("player_name", "")
            chat_content = extra.get("message", "")

            if player_name and chat_content:
                log_entry = {
                    "timestamp": datetime.now().isoformat(),
                    "server_time": message_contained.get("time", ""),
                    "player": player_name,
                    "message": chat_content,
                    "source": source,
                    "event_type": "player_chat",
                }

                _logger_instance.save_message(log_entry)
                _print_chat_message(log_entry)
            return

        # 备用：手动解析聊天消息格式
        # 只处理来自Minecraft服务器的INFO级别日志
        if level != "INFO" or "minecraft" not in source.lower():
            return

        # 检查是否是聊天消息格式: <玩家名> 消息内容
        match = CHAT_PATTERN.search(message)
        if match:
            player_name = match.group(1).strip()
            chat_content = match.group(2).strip()

            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "server_time": message_contained.get("time", ""),
                "player": player_name,
                "message": chat_content,
                "source": source,
                "level": level,
                "raw_message": message,
                "event_type": "log_parser",
            }

            _logger_instance.save_message(log_entry)
            _print_chat_message(log_entry)

    except Exception as e:
        logger.error(f"处理日志消息出错: {e}")


def _print_chat_message(log_entry: Dict[str, Any]):
    """格式化输出聊天消息到控制台"""
    try:
        # ANSI 颜色代码
        player_color = "\033[38;2;175;129;247m"  # 紫色
        message_color = "\033[97m"  # 白色
        reset_color = "\033[0m"

        # 简化时间显示
        time_display = _extract_time(log_entry)

        msg = (
            f"{player_color}[{time_display}] <{log_entry['player']}>{reset_color} "
            f"{message_color}{log_entry['message']}{reset_color}"
        )
        print(msg)

    except Exception as e:
        logger.error(f"输出聊天消息出错: {e}")


def _extract_time(log_entry: Dict[str, Any]) -> str:
    """提取并格式化时间"""
    # 尝试从 server_time 提取
    if log_entry.get("server_time"):
        try:
            time_str = log_entry["server_time"]
            if ":" in time_str:
                parts = time_str.split(":")
                if len(parts) >= 2:
                    return f"{parts[0]}:{parts[1]}"
        except Exception:
            pass

    # 尝试从 timestamp 提取
    if log_entry.get("timestamp"):
        try:
            dt = datetime.fromisoformat(log_entry["timestamp"].replace("Z", "+00:00"))
            return dt.strftime("%H:%M")
        except Exception:
            pass

    return datetime.now().strftime("%H:%M")


# ============ 公共 API ============

def search_chat_messages(keyword: Optional[str] = None, player: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """搜索聊天记录"""
    if _logger_instance is None:
        return []
    return _logger_instance.search(keyword=keyword, player=player, limit=limit)


def get_recent_chats(limit: int = 20) -> List[Dict[str, Any]]:
    """获取最近的聊天记录"""
    return search_chat_messages(limit=limit)


def get_player_chats(player_name: str, limit: int = 50) -> List[Dict[str, Any]]:
    """获取特定玩家的聊天记录"""
    return search_chat_messages(player=player_name, limit=limit)


def export_chat_log(format: str = "json", filename: Optional[str] = None) -> Tuple[bool, str]:
    """导出聊天记录"""
    if _logger_instance is None:
        return False, "聊天记录器未初始化"
    return _logger_instance.export(format=format, filename=filename)