"""YASL REST API — FastAPI + uvicorn，提供 /players 与 /command 端点。"""
import asyncio
import json
import re
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, Set, Dict, Any, List

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import uvicorn

from yasl.event_bus import subscribe, EventType
from yasl.main import MinecraftServer

# ---------------------------------------------------------------------------
# 配置加载（异步 I/O，避免阻塞事件循环）
# ---------------------------------------------------------------------------
_config_path = Path(__file__).parent / "config.json"


async def load_config_async() -> Dict[str, Any]:
    def _read():
        with open(_config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return await asyncio.get_event_loop().run_in_executor(None, _read)


async def save_config_async(config: Dict[str, Any]) -> None:
    def _write():
        with open(_config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    await asyncio.get_event_loop().run_in_executor(None, _write)


def load_config() -> Dict[str, Any]:
    """同步加载配置（兼容旧接口，仅在初始化阶段使用）。"""
    with open(_config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config: Dict[str, Any]) -> None:
    """同步保存配置（兼容旧接口）。"""
    with open(_config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 玩家状态（通过事件总线实时更新）
# ---------------------------------------------------------------------------
_players_online: Set[str] = set()
_players_lock = threading.Lock()


def _on_player_join(player_name: str, **kwargs: Any) -> None:
    with _players_lock:
        _players_online.add(player_name)


def _on_player_leave(player_name: str, **kwargs: Any) -> None:
    with _players_lock:
        _players_online.discard(player_name)


# 注册事件监听
subscribe(EventType.PLAYER_JOIN, _on_player_join)
subscribe(EventType.PLAYER_LEAVE, _on_player_leave)


# list 命令输出的 regex
_LIST_RE = re.compile(
    r"There are (\d+) of a max of (\d+) players? online:?\s*(.*)",
    re.IGNORECASE,
)


def get_players_info_sync() -> Dict[str, Any]:
    """同步读取事件总线维护的在线玩家集合（供 Dashboard 等同步上下文使用）。"""
    with _players_lock:
        players = sorted(_players_online)
    return {
        "count": len(players),
        "players": players,
    }


async def get_players_info() -> Dict[str, Any]:
    """通过 stdin 发送 list 命令，从 stdout 用正则提取在线玩家名称和总人数。

    若命令失败则回退到事件总线数据。
    """
    server = get_server()
    if server and server.running:
        result = await server.send_command_async("list", timeout=3.0)
        for line in result.get("lines", []):
            m = _LIST_RE.search(line)
            if m:
                count = int(m.group(1))
                max_players = int(m.group(2))
                names_str = m.group(3).strip()
                players = (
                    [n.strip() for n in names_str.split(",") if n.strip()]
                    if names_str
                    else []
                )
                return {
                    "count": count,
                    "players": players,
                    "max_players": max_players,
                }
    # 回退到事件总线
    return get_players_info_sync()


# ---------------------------------------------------------------------------
# Server 引用（外部注入）
# ---------------------------------------------------------------------------
_server_ref: Optional[MinecraftServer] = None


def set_server(server: MinecraftServer) -> None:
    """注入 MinecraftServer 实例，供 /command 使用。"""
    global _server_ref
    _server_ref = server


def get_server() -> Optional[MinecraftServer]:
    return _server_ref


# ---------------------------------------------------------------------------
# API Key 验证
# ---------------------------------------------------------------------------
security = HTTPBearer(auto_error=False)


async def verify_api_key(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> None:
    """验证 API Key：支持 Header (Authorization: Bearer <key>) 和 Query (?api_key=<key>)。"""
    config = await load_config_async()
    api_config = config.get("api", {})
    require_key = api_config.get("require_api_key", True)

    if not require_key:
        return

    expected_key = api_config.get("api_key", "")

    # 从 Header 获取
    if credentials and credentials.credentials == expected_key:
        return

    # 从 Query 参数获取
    query_key = request.query_params.get("api_key", "")
    if query_key == expected_key:
        return

    raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ---------------------------------------------------------------------------
# FastAPI 应用
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期（不做特别处理，server 由外部管理）。"""
    yield


app = FastAPI(
    title="YASL API",
    version="1.0.0",
    lifespan=lifespan,
)

# 全局依赖注入
API_KEY_DEP = Depends(verify_api_key)


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------


@app.get("/players", dependencies=[API_KEY_DEP])
async def players_endpoint() -> JSONResponse:
    """
    返回当前在线玩家信息。

    Response:
        {
            "count": 3,
            "players": ["Alice", "Bob", "Charlie"]
        }
    """
    info = await get_players_info()
    return JSONResponse(content=info)


@app.post("/command", dependencies=[API_KEY_DEP])
async def command_endpoint(request: Request) -> JSONResponse:
    """
    向 Minecraft 服务器发送命令，返回执行结果。

    Request Body:
        {
            "command": "list",
            "timeout": 5.0
        }

    Response:
        {
            "command": "list",
            "success": true,
            "output": "There are 3 of a max of 20 players online: ..."
        }
    """
    body = await request.json()
    command = body.get("command", "")
    if not command:
        raise HTTPException(status_code=400, detail="Missing 'command' field")

    timeout = float(body.get("timeout", 5.0))

    server = get_server()
    if not server:
        raise HTTPException(status_code=503, detail="Server not connected")

    result = await server.send_command_async(command.strip(), timeout=timeout)

    return JSONResponse(
        content={
            "command": command.strip(),
            "success": not result.get("timed_out", False),
            "lines": result.get("lines", []),
            "count": result.get("count", 0),
        }
    )


@app.post("/reload", dependencies=[API_KEY_DEP])
async def reload_config() -> JSONResponse:
    """重新加载 config.json。"""
    config = await load_config_async()
    return JSONResponse(content={"status": "ok", "config": config})


@app.get("/health")
async def health_endpoint() -> JSONResponse:
    """健康检查（不需要 API Key）。"""
    server = get_server()
    return JSONResponse(
        content={
            "status": "ok",
            "server_connected": server is not None and server.running,
        }
    )


# ---------------------------------------------------------------------------
# 启动
# ---------------------------------------------------------------------------


def run_api(host: str = "0.0.0.0", port: int = 8000) -> None:
    """启动 API 服务器（阻塞式，通常在线程中调用）。"""
    uvicorn.run(app, host=host, port=port, log_level="warning")