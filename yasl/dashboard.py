"""Gradio 监控面板 — 端口 8001，实时显示服务器状态与在线玩家。"""
import threading
from datetime import datetime

import gradio as gr

from yasl.api import get_server, get_players_info
from yasl.event_bus import subscribe, EventType

# ---------------------------------------------------------------------------
# 全局状态
# ---------------------------------------------------------------------------
_latest_logs: list[str] = []
_logs_lock = threading.Lock()
MAX_LOGS = 200


def _on_log(time: str = "", source: str = "", message: str = "", **kwargs):
    with _logs_lock:
        _latest_logs.append(f"[{time}] [{source}] {message}")
        if len(_latest_logs) > MAX_LOGS:
            _latest_logs[:] = _latest_logs[-MAX_LOGS:]


subscribe("log", _on_log)


# ---------------------------------------------------------------------------
# 数据获取
# ---------------------------------------------------------------------------
def _fetch_status() -> str:
    srv = get_server()
    if not srv:
        return "⚫ 未连接"
    if srv.running:
        pid = srv.process.pid if srv.process else "?"
        return f"🟢 运行中  PID: {pid}"
    return "🔴 已停止"


def _fetch_players() -> str:
    info = get_players_info()
    count = info["count"]
    if count == 0:
        return "暂无在线玩家"
    return f"{count} 人在线: {', '.join(info['players'])}"


def _fetch_logs() -> str:
    with _logs_lock:
        return "\n".join(_latest_logs) or "(暂无日志)"


def _fetch_uptime() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# 界面构建
# ---------------------------------------------------------------------------
def build_ui() -> gr.Blocks:
    with gr.Blocks(title="YASL 监控面板", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# 🎮 YASL Minecraft 服务器监控")

        with gr.Row():
            status = gr.Textbox(label="服务器状态", value=_fetch_status(), interactive=False)
            players = gr.Textbox(label="在线玩家", value=_fetch_players(), interactive=False,
                                 lines=1)

        with gr.Row():
            logs = gr.Textbox(
                label="最近日志", value=_fetch_logs(), interactive=False,
                lines=15, max_lines=20,
            )

        timestamp = gr.Textbox(
            label="面板更新时间", value=_fetch_uptime(), interactive=False,
            every=2,
        )

        # 定时刷新（Gradio 5.x 使用 gr.Timer 替代 demo.load(..., every=)）
        timer3 = gr.Timer(3, active=True)
        timer2 = gr.Timer(2, active=True)
        timer3.tick(_fetch_status, outputs=status)
        timer3.tick(_fetch_players, outputs=players)
        timer2.tick(_fetch_logs, outputs=logs)

    return demo


# ---------------------------------------------------------------------------
# 启动
# ---------------------------------------------------------------------------
def run_dashboard(host: str = "0.0.0.0", port: int = 8001, share: bool = False) -> None:
    ui = build_ui()
    ui.queue(default_concurrency_limit=5)
    ui.launch(server_name=host, server_port=port, share=share, quiet=True)