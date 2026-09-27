"""
Modelos de datos para la aplicación ProCamera
"""
from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime
from enum import Enum
import numpy as np
from utils.logger import get_logger

logger = get_logger("Models")


class CameraStatus(Enum):
    """Estado de la cámara"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    RECORDING = "recording"


class ImageFormat(Enum):
    """Formatos de imagen soportados"""
    JPG = "jpg"
    PNG = "png"
    BMP = "bmp"
    TIFF = "tiff"
    
    @classmethod
    def get_extensions(cls):
        return [f.value for f in cls]
    
    @classmethod
    def get_default(cls):
        return cls.JPG


class VideoFormat(Enum):
    """Formatos de video soportados"""
    MP4 = "mp4"
    MKV = "mkv"
    AVI = "avi"
    MPG = "mpg"
    MOV = "mov"
    
    @classmethod
    def get_extensions(cls):
        return [f.value for f in cls]
    
    @classmethod
    def get_default(cls):
        return cls.AVI


class Resolution(Enum):
    """Resoluciones soportadas"""
    QVGA = ("QVGA (320x240)", 320, 240)
    VGA = ("VGA (640x480)", 640, 480)
    SVGA = ("SVGA (800x600)", 800, 600)
    XGA = ("XGA (1024x768)", 1024, 768)
    HD = ("HD (1280x720)", 1280, 720)
    FULL_HD = ("Full HD (1920x1080)", 1920, 1080)
    FOUR_K = ("4K (4080x2296)", 4080, 2296)
    
    def __new__(cls, display_name: str, width: int, height: int):
        obj = object.__new__(cls)
        obj._value_ = display_name
        obj.display_name = display_name
        obj.width = width
        obj.height = height
        return obj
    
    @classmethod
    def get_default(cls):
        return cls.VGA
    
    @classmethod
    def get_options(cls):
        return [r.display_name for r in cls]
    
    def get_size(self) -> tuple:
        return (self.width, self.height)


class QualityProfile(Enum):
    """Perfiles de calidad"""
    LOW = ("Baja - Archivos pequeños", 30)
    MEDIUM = ("Media - Balance calidad/tamaño", 60)
    HIGH = ("Alta - Buena calidad", 85)
    ULTRA = ("Ultra - Máxima calidad", 95)
    
    def __new__(cls, display_name: str, value: int):
        obj = object.__new__(cls)
        obj._value_ = display_name
        obj.display_name = display_name
        obj.quality_value = value
        return obj
    
    @classmethod
    def get_default(cls):
        return cls.HIGH
    
    @classmethod
    def get_options(cls):
        return [p.display_name for p in cls]
    
    def get_quality(self) -> int:
        return self.quality_value


@dataclass
class CameraDevice:
    """Representa una cámara IP, de pantalla o local"""
    id: int
    name: str
    ip: str
    port: int
    url_type: str = "video"
    is_active: bool = False
    status: CameraStatus = CameraStatus.DISCONNECTED
    current_frame: Optional[np.ndarray] = None
    thread = None
    is_screen: bool = False
    is_local: bool = False  # NUEVO: cámara física del dispositivo
    auto_flash: bool = False
    camera_index: int = 0  # NUEVO: índice de cámara local (0, 1, 2...)
    
    @property
    def video_url(self) -> str:
        if self.is_screen:
            return "screen://"
        elif self.is_local:
            return f"local://{self.camera_index}"
        elif self.url_type == "shot":
            return f"http://{self.ip}:{self.port}/shot.jpg"
        else:
            return f"http://{self.ip}:{self.port}/video"
    
    @property
    def display_name(self) -> str:
        if self.is_screen:
            return f"🖥️ {self.name} (Pantalla)"
        if self.is_local:
            return f"📹 {self.name} (Cámara Local)"
        return f"{self.name} ({self.ip}:{self.port})"
    
    @property
    def camera_type(self) -> str:
        """Tipo de cámara para clasificación"""
        if self.is_screen:
            return "screen"
        if self.is_local:
            return "local"
        return "ip"


@dataclass
class CaptureSettings:
    """Configuración de captura"""
    default_name: str = "foto_{timestamp}"
    default_directory: str = "~/Pictures/Capturas"
    image_resolution: Resolution = Resolution.FOUR_K
    video_resolution: Resolution = Resolution.HD
    image_format: ImageFormat = ImageFormat.JPG
    video_format: VideoFormat = VideoFormat.MP4
    image_quality: int = 85
    video_quality: int = 80
    video_fps: int = 30
    video_codec: str = "MJPG"
    
    def get_image_size(self) -> tuple:
        return (self.image_resolution.width, self.image_resolution.height)
    
    def get_video_size(self) -> tuple:
        return (self.video_resolution.width, self.video_resolution.height)
    
    def get_image_extension(self) -> str:
        return f".{self.image_format.value}"
    
    def get_video_extension(self) -> str:
        return f".{self.video_format.value}"


@dataclass
class CaptureItem:
    """Representa un archivo capturado"""
    path: str
    timestamp: datetime
    camera_name: str
    item_type: str
    format: str
    size: int
    resolution: str
    quality: int
    
    @property
    def filename(self) -> str:
        return self.path.split('/')[-1].split('\\')[-1]
    
    @property
    def size_mb(self) -> float:
        return self.size / (1024 * 1024)


@dataclass
class LocalCameraInfo:
    """Información de una cámara local detectada"""
    index: int
    name: str
    backend: str = "dshow"
    available: bool = True