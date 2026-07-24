"""扩展加载器 — 扫描 extensions/ 目录，管理扩展生命周期与事件接口。"""
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from yasl.event_bus import subscribe, unsubscribe, publish
from yasl.installer import install_requirements
from yasl.commands import CommandHelper
from yasl.logging import ExtensionLogger

_log = ExtensionLogger("ExtManager")


# ---------------------------------------------------------------------------
# 扩展基类
# ---------------------------------------------------------------------------
class ExtensionBase:
    """所有扩展必须继承此类。"""

    name: str = "unnamed"
    version: str = "0.0.0"
    author: str = ""
    repo: str = ""

    def __init__(self) -> None:
        # 由 ExtensionManager 在 load 时注入
        self.commands: CommandHelper = CommandHelper()

    async def on_load(self) -> None:
        """扩展被加载时调用。"""
        pass

    async def on_enable(self) -> None:
        """扩展被启用时调用（可注册事件监听）。"""
        pass

    async def on_disable(self) -> None:
        """扩展被禁用时调用（应注销事件监听）。"""
        pass

    async def on_unload(self) -> None:
        """扩展被卸载时调用。"""
        pass

    # ---------- 提供给扩展的事件接口 ----------
    def subscribe(self, event_type: str, callback) -> None:
        subscribe(event_type, callback)

    def unsubscribe(self, event_type: str, callback) -> None:
        unsubscribe(event_type, callback)

    def fire(self, event_type: str, **kwargs) -> None:
        publish(event_type, **kwargs)


# ---------------------------------------------------------------------------
# 扩展加载器
# ---------------------------------------------------------------------------
class ExtensionManager:
    """管理所有扩展的加载、启用、禁用、卸载。"""

    def __init__(self, extensions_dir: Optional[Path] = None, commands: Optional[CommandHelper] = None):
        if extensions_dir is None:
            extensions_dir = Path(__file__).parent.parent / "extensions"
        self._dir = extensions_dir
        self._dir.mkdir(parents=True, exist_ok=True)

        # 命令接口（供扩展调用）
        self._commands = commands or CommandHelper()

        # 已安装扩展记录（扩展名 → 版本 / 元信息）
        self._state_file = self._dir / ".installed.json"
        self._installed: Dict[str, Any] = self._load_state()

        # 已加载的扩展实例
        self._extensions: Dict[str, ExtensionBase] = {}

    # ------------------------------------------------------------------
    # 状态持久化
    # ------------------------------------------------------------------
    def _load_state(self) -> Dict[str, Any]:
        if self._state_file.exists():
            try:
                with open(self._state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_state(self) -> None:
        with open(self._state_file, "w", encoding="utf-8") as f:
            json.dump(self._installed, f, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # 扫描 & 安装
    # ------------------------------------------------------------------
    async def discover(self) -> List[str]:
        """扫描 extensions/ 目录，返回新发现的扩展名列表。"""
        discovered: List[str] = []
        if not self._dir.is_dir():
            return discovered

        for entry in sorted(self._dir.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue

            main_file = entry / "main.py"
            if not main_file.is_file():
                continue

            name = entry.name
            if name not in self._installed:
                # 新扩展 → 安装依赖
                req_file = entry / "requirements.txt"
                if req_file.is_file():
                    print(f"  [Extension] 安装 {name} 依赖...")
                    await install_requirements(req_file)

                # 占位版本，实际版本在 load() 时从类定义中读取
                self._installed[name] = "0.0.0"
                self._save_state()
                _log.info(f"发现新扩展: {name}")
                discovered.append(name)

        return discovered

    # ------------------------------------------------------------------
    # 加载 / 卸载
    # ------------------------------------------------------------------
    def load(self, name: str) -> Optional[ExtensionBase]:
        """加载指定扩展并返回实例。"""
        main_file = self._dir / name / "main.py"
        if not main_file.is_file():
            return None

        spec = importlib.util.spec_from_file_location(
            f"extensions.{name}", str(main_file)
        )
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        sys.modules[f"extensions.{name}"] = module
        spec.loader.exec_module(module)

        # 查找 ExtensionBase 子类
        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if (
                isinstance(obj, type)
                and issubclass(obj, ExtensionBase)
                and obj is not ExtensionBase
            ):
                ext = obj()
                ext.name = name
                ext.commands = self._commands  # 注入命令接口
                self._extensions[name] = ext

                # 从类定义中读取元信息并持久化
                self._installed[name] = {
                    "version": ext.version,
                    "author": ext.author,
                    "repo": ext.repo,
                }
                self._save_state()
                return ext

        return None

    def unload(self, name: str) -> None:
        """卸载扩展。"""
        if name in self._extensions:
            del self._extensions[name]
        mod_name = f"extensions.{name}"
        if mod_name in sys.modules:
            del sys.modules[mod_name]

    # ------------------------------------------------------------------
    # 生命周期批量操作
    # ------------------------------------------------------------------
    async def load_all(self) -> None:
        """加载所有已发现的扩展。"""
        await self.discover()
        for name in list(self._installed.keys()):
            if name not in self._extensions:
                ext = self.load(name)
                if ext:
                    await ext.on_load()
                    _log.info(f"已加载: {name}")

    async def enable_all(self) -> None:
        """启用所有已加载的扩展（单个失败不影响其他）。"""
        for name, ext in self._extensions.items():
            try:
                await ext.on_enable()
            except Exception as e:
                _log.error(f"启用 {name} 失败: {e}")

    async def disable_all(self) -> None:
        """禁用所有已启用的扩展（单个失败不影响其他）。"""
        for name, ext in self._extensions.items():
            try:
                await ext.on_disable()
            except Exception as e:
                _log.error(f"禁用 {name} 失败: {e}")

    async def unload_all(self) -> None:
        """卸载所有扩展。"""
        for name in list(self._extensions.keys()):
            await self._extensions[name].on_unload()
            self.unload(name)

    @property
    def loaded_extensions(self) -> Dict[str, ExtensionBase]:
        return dict(self._extensions)

    # ------------------------------------------------------------------
    # 元信息查询
    # ------------------------------------------------------------------
    def get_extension_meta(self, name: str) -> Optional[Dict[str, Any]]:
        """获取扩展元数据：name, version, author, repo。"""
        ext = self._extensions.get(name)
        if ext is None:
            return None
        return {
            "name": ext.name,
            "version": ext.version,
            "author": ext.author,
            "repo": ext.repo,
        }

    def list_extensions(self) -> List[Dict[str, Any]]:
        """列出所有已加载扩展的元数据。"""
        result: List[Dict[str, Any]] = []
        for name in self._extensions:
            meta = self.get_extension_meta(name)
            if meta:
                result.append(meta)
        return result