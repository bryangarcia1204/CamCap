"""
Interfaces (Protocolos) y dataclasses del sistema de plugins.

Aquí se definen los CONTRATOS que las APIs deben cumplir.
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable, Protocol, Tuple, runtime_checkable
from .hooks import HookRegistry

import numpy as np
import contextvars

# Variable de contexto que identifica el plugin actual
_current_plugin: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_plugin", default=""
)


# ==================== METADATOS ====================

@dataclass
class PluginMetadata:
    """Metadatos de un plugin."""
    name: str
    version: str = "0.0.0"
    description: str = ""
    author: str = ""
    dependencies: List[str] = field(default_factory=list)
    requires_debug: bool = False
    enabled_by_default: bool = True
    auto_load: bool = True
    path: str = ""
    module_name: str = ""
    capabilities: List[str] = field(default_factory=list)   # ✅ NUEVO


# ==================== CONTEXTO ====================

class PluginContext:
    """
    Contexto que se pasa a cada plugin.

    Contiene TODAS las APIs que un plugin puede usar.
    """

    def __init__(self):
        # === APIs ===
        self.settings: Optional['SettingsAPI'] = None
        self.cameras: Optional['CamerasAPI'] = None
        self.frames: Optional['FramesAPI'] = None
        self.ui: Optional['UIAPI'] = None
        self.files: Optional['FilesAPI'] = None
        self.notifications: Optional['NotificationsAPI'] = None
        self.logger: Optional['LoggerAPI'] = None
        self.timers: Optional['TimersAPI'] = None
        self.hooks: Optional['HookRegistry'] = None
        self.settings: Optional['SettingsAPI'] = None
        self.cameras: Optional['CamerasAPI'] = None
        self.frames: Optional['FramesAPI'] = None
        self.ui: Optional['UIAPI'] = None
        self.files: Optional['FilesAPI'] = None
        self.notifications: Optional['NotificationsAPI'] = None
        self.logger: Optional['LoggerAPI'] = None
        self.timers: Optional['TimersAPI'] = None
        self.hooks: Optional['HookRegistry'] = None
        self.extensions: Optional[Any] = None
        self.services: Optional[Any] = None

        # ✅ NUEVO: info del plugin actual (para capability checks)
        self.plugin_name: str = ""   # se setea desde PluginManager

        # Info del sistema
        self.app_version: str = "2.0.0"
        self.is_debug: bool = False
        self.plugin_dir: str = ""

    def __repr__(self) -> str:
        apis = []
        for name in ("settings", "cameras", "frames", "ui", "files",
                     "notifications", "logger", "timers", "hooks"):
            if getattr(self, name, None) is not None:
                apis.append(name)
        return (
            f"<PluginContext plugin='{self.plugin_name}' "
            f"apis={apis} debug={self.is_debug}>"
        )


# ==================== PROTOCOLOS DE APIs ====================

@runtime_checkable
class SettingsAPI(Protocol):
    """API de configuración."""

    def get(self, key: str, default: Any = None) -> Any: ...
    def set(self, key: str, value: Any) -> bool: ...
    def get_plugin_config(self, plugin_name: str) -> Dict[str, Any]: ...
    def set_plugin_config(self, plugin_name: str, config: Dict[str, Any]) -> bool: ...
    def get_advanced_all(self) -> Dict[str, Any]: ...
    def register_config_schema(self, plugin_name: str, schema: Dict[str, Any]): ...


@runtime_checkable
class CamerasAPI(Protocol):
    """API de cámaras."""

    def get_all_cameras(self) -> List[Any]: ...
    def get_active_cameras(self) -> List[Any]: ...
    def get_camera(self, camera_id: int) -> Optional[Any]: ...
    def get_thread(self, camera_id: int) -> Optional[Any]: ...
    def register_frame_processor(self, callback: Callable, priority: int = 50): ...
    def unregister_frame_processor(self, callback: Callable): ...


@runtime_checkable
class FramesAPI(Protocol):
    """API de procesamiento de frames."""

    def register_pre_processor(self, callback: Callable, priority: int = 50): ...
    def register_post_processor(self, callback: Callable, priority: int = 50): ...
    def get_last_frame(self, camera_id: int) -> Optional[np.ndarray]: ...


@runtime_checkable
class UIAPI(Protocol):
    """API de la GUI."""

    def add_toolbar_button(self, text: str, icon: str,
                           callback: Callable, tooltip: str = "") -> Any: ...
    def add_menu_action(self, menu_name: str, text: str,
                        callback: Callable, shortcut: str = None) -> Any: ...
    def add_settings_tab(self, title: str, widget: Any, icon: str = ""): ...
    def add_dock_widget(self, title: str, widget: Any,
                        area: str = "bottom") -> Any: ...
    def show_status_message(self, message: str, timeout_ms: int = 3000): ...
    def show_notification(self, title: str, message: str): ...


@runtime_checkable
class FilesAPI(Protocol):
    """API de archivos."""

    def save_image(self, frame: np.ndarray, directory: str, filename: str,
                   format: str = "jpg", quality: int = 85) -> Tuple[str, int]: ...
    def save_text(self, text: str, path: str) -> bool: ...
    def read_text(self, path: str) -> str: ...
    def get_capture_directory(self) -> str: ...


@runtime_checkable
class NotificationsAPI(Protocol):
    """API de notificaciones."""

    def notify(self, title: str, message: str,
               image_path: Optional[str] = None) -> bool: ...
    def notify_telegram(self, message: str,
                        image_path: Optional[str] = None) -> bool: ...


@runtime_checkable
class LoggerAPI(Protocol):
    """API de logging."""

    def debug(self, msg: str): ...
    def info(self, msg: str): ...
    def warning(self, msg: str): ...
    def error(self, msg: str, exc_info: bool = False): ...


@runtime_checkable
class TimersAPI(Protocol):
    """API de timers."""

    def create(self, name: str, interval_ms: int,
               callback: Callable, single_shot: bool = False): ...
    def stop(self, name: str): ...
    def destroy(self, name: str): ...