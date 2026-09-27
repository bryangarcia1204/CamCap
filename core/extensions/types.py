"""
Tipos y enums usados por el sistema de extensiones.
"""
from enum import Enum, IntEnum
from dataclasses import dataclass
from typing import Optional, List, Dict, Any


class Priority(IntEnum):
    """Prioridad de extensiones (menor = se ejecuta primero)."""
    HIGHEST = 10
    HIGH = 25
    NORMAL = 50
    LOW = 75
    LOWEST = 100


class CameraProtocol(Enum):
    """Protocolo de cámara."""
    HTTP_MJPEG = "http_mjpeg"
    RTSP = "rtsp"
    USB = "usb"
    WEBCAM = "webcam"
    FILE = "file"
    SCREEN = "screen"
    CUSTOM = "custom"


class FrameFormat(Enum):
    """Formato de frame."""
    BGR = "bgr"
    RGB = "rgb"
    GRAY = "gray"
    RGBA = "rgba"
    YUV = "yuv"


class NotificationLevel(Enum):
    """Nivel de notificación."""
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class ThemeMode(Enum):
    """Modo de tema."""
    LIGHT = "light"
    DARK = "dark"
    AUTO = "auto"


class Capability(Enum):
    """
    Capacidades que un plugin puede solicitar.

    El Core verifica estos permisos antes de conceder acceso.
    """
    # === Files ===
    READ_FILES = "read_files"
    WRITE_FILES = "write_files"
    FILE_DELETE = "file_delete"

    # === Network ===
    NETWORK = "network"
    TELEGRAM = "telegram"

    # === Hardware ===
    CAMERA_ACCESS = "camera_access"
    CAMERA_CONTROL = "camera_control"
    AUDIO_ACCESS = "audio_access"

    # === System ===
    SYSTEM_INFO = "system_info"
    PROCESS_EXECUTION = "process_execution"

    # === Config ===
    SETTINGS_READ = "settings_read"
    SETTINGS_WRITE = "settings_write"

    # === UI ===
    UI_MODIFY = "ui_modify"
    NOTIFICATIONS = "notifications"


@dataclass
class CameraInfo:
    """Info de una cámara para extensiones."""
    id: int
    name: str
    protocol: CameraProtocol
    url: str
    metadata: Dict[str, Any] = None


@dataclass
class PluginInfo:
    """Info de un plugin."""
    name: str
    version: str
    description: str = ""
    author: str = ""
    capabilities: List[Capability] = None