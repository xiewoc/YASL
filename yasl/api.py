# . / yasl / api.py
import os
import asyncio
import threading
import time
import logging
from typing import List, Dict, Optional
from pydantic import BaseModel
from fastapi import FastAPI, Depends, Header, HTTPException, status, WebSocket
import uvicorn

# 设置日志
logger = logging.getLogger(__name__)

# 全局服务器实例
_server_instance = None


def get_playtime_manager():
    """获取玩家游戏时间管理器实例"""
    server = get_server()
    if server and hasattr(server, 'playtime_manager'):
        return server.playtime_manager
    return None


def get_server():
    """获取服务器实例"""
    return _server_instance


def set_server(server):
    """设置服务器实例"""
    global _server_instance
    _server_instance = server
    logger.info(f"Server instance set: {server}")


class CommandRequest(BaseModel):
    command: str
    timeout: float = 5.0


class PlayerListResponse:
    """用于跟踪 list 命令响应的类"""

    def __init__(self):
        self.players: List[str] = []
        self.event = asyncio.Event()
        self.received = False


async def list_player_async(timeout: float = 5.0) -> List[str]:
    """
    异步向服务器发送 list 命令并解析返回的在线玩家名称列表
    
    Args:
        timeout: 等待响应的超时时间（秒）
    
    Returns:
        在线玩家名称列表
    """
    server = get_server()

    if not server:
        logger.error("Server instance not available")
        return []

    if not hasattr(server, "process") or not server.process:
        logger.error("Server process not available")
        return []

    result: List[str] = []
    found = asyncio.Event()

    async def on_log_event(event_message):
        """处理日志事件，解析玩家列表"""
        if found.is_set():
            return

        message = event_message.message_contained.get("message", "")
        if not message or "players online:" not in message:
            return

        try:
            # 提取玩家名字
            parts = message.split("online:", 1)
            if len(parts) > 1:
                players_str = parts[1].strip().rstrip(".")
                
                if players_str:
                    # 分割玩家名称
                    names = [n.strip() for n in players_str.split(",") if n.strip()]
                    result.extend(names)
                    found.set()
                    logger.info(f"Parsed players: {names}")
        except Exception as e:
            logger.error(f"Error parsing players: {e}")

    try:
        from yasl.event_bus import subscribe

        # 订阅日志事件
        unsubscribe_func = subscribe("log", on_log_event)

        # 发送 list 命令
        server.send_command("list")

        # 等待响应
        await asyncio.wait_for(found.wait(), timeout)
        return result

    except asyncio.TimeoutError:
        logger.warning("List command timed out")
        return result
    except Exception as e:
        logger.error(f"Error in list_player_async: {e}")
        return result
    finally:
        try:
            unsubscribe_func()
        except Exception:
            pass


# 保留向后兼容的别名
list_player_simple_async = list_player_async


# ---- FastAPI 部分 ----
app = FastAPI(title="YASL Minecraft API")

# 响应模型
class PlayersResponse(BaseModel):
    players: List
    count: int
    timestamp: float

class CommandResponse(BaseModel):
    status: str
    command: str
    result: Optional[str]
    timeout: float

class StatusResponse(BaseModel):
    server_available: bool
    process_running: bool
    jvm_running: bool
    jvm_pid: Optional[int]
    timestamp: float

class PlaytimeResponse(BaseModel):
    players: List
    count: int
    total_count: int
    timestamp: float

class PlaytimeStatsResponse(BaseModel):
    total_players: int
    online_players: int
    timestamp: float

class PlaytimeSearchResponse(BaseModel):
    players: List
    count: int
    timestamp: float

class PlaytimePlayerResponse(BaseModel):
    player: Optional[Dict]
    timestamp: float

class RefreshResponse(BaseModel):
    status: str
    player_count: int
    online_count: int
    timestamp: float

class DeleteResponse(BaseModel):
    status: str
    player: str
    timestamp: float

class TestResponse(BaseModel):
    event_bus: str
    server: str


API_KEY = os.environ.get("YASL_API_KEY", "")


def _verify_api_key(authorization: str | None = Header(default=None)) -> None:
    """简单的 Bearer token 验证。"""
    if not API_KEY:
        return
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format",
        )
    token = authorization.split("Bearer ", 1)[1].strip()
    if token != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key"
        )


def _get_server_or_404():
    """获取服务器实例或抛出404"""
    server = get_server()
    if not server:
        raise HTTPException(status_code=503, detail="Server not available")
    return server


def _get_pt_manager_or_404():
    """获取PlayTime管理器或抛出404"""
    pt_manager = get_playtime_manager()
    if not pt_manager:
        raise HTTPException(status_code=503, detail="PlayTime manager not available")
    return pt_manager


@app.get("/")
async def root():
    return {"name": "YASL Minecraft API", "status": "running"}


@app.get("/players", response_model=PlayersResponse)
async def api_list_players(dep=Depends(_verify_api_key)):
    """异步获取在线玩家列表"""
    players = await list_player_simple_async() or await list_player_async()
    return PlayersResponse(
        players=players,
        count=len(players),
        timestamp=time.time()
    )


@app.post("/command", response_model=CommandResponse)
async def api_send_command(req: CommandRequest, dep=Depends(_verify_api_key)):
    """异步向服务器发送命令并返回结果"""
    server = _get_server_or_404()
    result = await server.send_command_async(req.command, timeout=req.timeout)
    return CommandResponse(
        status="ok",
        command=req.command,
        result=result,
        timeout=req.timeout
    )


@app.get("/status", response_model=StatusResponse)
async def api_status(dep=Depends(_verify_api_key)):
    """异步获取服务器状态"""
    server = get_server()
    
    # 检查 JVM 进程是否真正运行
    jvm_running = False
    jvm_pid = None
    
    if server and hasattr(server, "process") and server.process:
        jvm_pid = server.process.pid
        try:
            # 检查进程是否真正存活（防止 BrokenPipe）
            try:
                import psutil
                proc = psutil.Process(jvm_pid)
                jvm_running = proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
            except ImportError:
                # psutil 不可用，使用 poll() 检查
                jvm_running = server.process.poll() is None
            except Exception:
                jvm_running = False
        except Exception:
            jvm_running = server.process.poll() is None
    
    return StatusResponse(
        server_available=server is not None,
        process_running=server is not None and hasattr(server, "process") and server.process is not None,
        jvm_running=jvm_running,
        jvm_pid=jvm_pid,
        timestamp=time.time(),
    )


@app.get("/test", response_model=TestResponse)
async def test_endpoint():
    """测试端点"""
    server = get_server()
    event_bus_status = "unknown"
    
    try:
        from yasl.event_bus import publish_async
        await publish_async("test", message="Test from API")
        event_bus_status = "publish_ok"
    except Exception as e:
        event_bus_status = f"error: {str(e)}"
    
    return TestResponse(
        event_bus=event_bus_status,
        server="available" if server else "not_available"
    )


# ===== 玩家游戏时间 API =====
@app.get("/playtime", response_model=PlaytimeResponse)
async def api_get_all_playtime(
    sort_by: str = "total_seconds",
    order: str = "desc",
    limit: int = 100,
    dep=Depends(_verify_api_key)
):
    """获取所有玩家的游戏时间统计"""
    pt_manager = _get_pt_manager_or_404()
    reverse = order.lower() == "desc"
    players = pt_manager.get_all_players(sort_by=sort_by, reverse=reverse)
    return PlaytimeResponse(
        players=players[:limit],
        count=len(players[:limit]),
        total_count=len(players),
        timestamp=time.time()
    )


@app.get("/playtime/stats", response_model=PlaytimeStatsResponse)
async def api_get_playtime_stats(dep=Depends(_verify_api_key)):
    """获取游戏时间统计概览"""
    pt_manager = _get_pt_manager_or_404()
    stats = pt_manager.get_stats()
    return PlaytimeStatsResponse(
        total_players=stats["total_players"],
        online_players=stats["online_players"],
        timestamp=time.time()
    )


@app.get("/playtime/search", response_model=PlaytimeSearchResponse)
async def api_search_players(
    q: str,
    limit: int = 20,
    dep=Depends(_verify_api_key)
):
    """搜索玩家"""
    pt_manager = _get_pt_manager_or_404()
    players = pt_manager.search_players(q, limit=limit)
    return PlaytimeSearchResponse(
        players=players,
        count=len(players),
        timestamp=time.time()
    )


@app.get("/playtime/{player_name}", response_model=PlaytimePlayerResponse)
async def api_get_player_playtime(player_name: str, dep=Depends(_verify_api_key)):
    """获取指定玩家的游戏时间统计"""
    pt_manager = _get_pt_manager_or_404()
    summary = pt_manager.get_player_summary(player_name)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Player {player_name} not found")
    return PlaytimePlayerResponse(player=summary, timestamp=time.time())


@app.get("/playtime/online/current", response_model=PlaytimeSearchResponse)
async def api_get_online_players_playtime(dep=Depends(_verify_api_key)):
    """获取当前在线玩家的游戏时间"""
    pt_manager = _get_pt_manager_or_404()
    players = pt_manager.get_online_players()
    return PlaytimeSearchResponse(players=players, count=len(players), timestamp=time.time())


@app.post("/playtime/refresh", response_model=RefreshResponse)
async def api_refresh_playtime(dep=Depends(_verify_api_key)):
    """刷新玩家游戏时间数据（从文件重新加载）"""
    pt_manager = _get_pt_manager_or_404()
    pt_manager.save()
    stats = pt_manager.get_stats()
    return RefreshResponse(
        status="ok",
        player_count=stats["total_players"],
        online_count=stats["online_players"],
        timestamp=time.time()
    )


@app.delete("/playtime/{player_name}", response_model=DeleteResponse)
async def api_delete_player_playtime(player_name: str, dep=Depends(_verify_api_key)):
    """删除玩家游戏时间数据"""
    pt_manager = _get_pt_manager_or_404()
    success = pt_manager.reset_player(player_name)
    if not success:
        raise HTTPException(status_code=404, detail=f"Player {player_name} not found")
    return DeleteResponse(status="ok", player=player_name, timestamp=time.time())


# WebSocket端点
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            # 处理WebSocket消息
            await websocket.send_text(f"Echo: {data}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")


# API 服务器控制
_uvicorn_server = None
_uvicorn_thread = None


async def start_api(host: str = "0.0.0.0", port: int = 8000):
    """异步启动 API 服务器"""
    global _uvicorn_server, _uvicorn_thread

    if _uvicorn_thread and _uvicorn_thread.is_alive():
        return

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    _uvicorn_server = uvicorn.Server(config)

    def run_server():
        asyncio.run(_uvicorn_server.serve())

    _uvicorn_thread = threading.Thread(target=run_server, daemon=True)
    _uvicorn_thread.start()

    logger.info(f"API server started on {host}:{port}")


async def stop_api():
    """异步停止 API 服务器"""
    global _uvicorn_server, _uvicorn_thread

    if _uvicorn_server:
        _uvicorn_server.should_exit = True
        await asyncio.sleep(0.1)  # 给服务器一点时间关闭

    _uvicorn_thread = None
    _uvicorn_server = None


# 初始化日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
