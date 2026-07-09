"""服务器文件检测器 — 支持 Forge / Paper / 自定义 server_type 与 forge_version。"""
from pathlib import Path
import os


class Load:
    __slots__ = ("cwd", "server_path", "forge_path", "paper_path", "_server_type_override")

    def __init__(self, forge_version: str = "", server_type: str = "") -> None:
        self.cwd = Path(__file__).parent / ".."
        self.server_path = self.cwd / "server"

        self.forge_path: Path | None = None
        self.paper_path: Path | None = None
        self._server_type_override = server_type

        # -------- Forge --------
        forge_base = self.server_path / "libraries" / "net" / "minecraftforge" / "forge"
        if forge_base.is_dir():
            versions = sorted(d for d in forge_base.iterdir() if d.is_dir())
            chosen = None
            if forge_version:
                for v in versions:
                    if v.name == forge_version:
                        chosen = v
                        break
            if chosen is None and versions:
                chosen = versions[0]
            if chosen:
                self.forge_path = chosen

        # -------- Paper / Purpur / Spigot --------
        if self.server_path.is_dir():
            for f in sorted(self.server_path.iterdir()):
                if f.name.endswith(".jar") and f.name.startswith(("paper-", "purpur-", "spigot-")):
                    self.paper_path = f
                    break

    # ------------------------------------------------------------------
    def serverfile_path(self) -> Path | None:
        st = self.server_type()
        if st == "forge":
            return self.forge_path
        if st == "paper":
            return self.paper_path
        return None

    def server_type(self) -> str | None:
        if self._server_type_override:
            return self._server_type_override

        has_forge = self.forge_path is not None
        has_paper = self.paper_path is not None

        if has_forge and not has_paper:
            return "forge"
        if not has_forge and has_paper:
            return "paper"
        if has_forge and has_paper:
            raise FileExistsError("同时检测到 Forge 和 Paper 文件，请检查 server/ 目录")
        return None