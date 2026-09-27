"""
API pública del sistema de plugins de ProCamera.
"""
from .base_plugin import BasePlugin
from .plugin_manager import (
    PluginManager,
    get_plugin_manager,
    set_plugin_manager,
    PluginError,
    PluginNotFoundError,
    PluginDependencyError,
    PluginLoadError,
)
from .hooks import HookRegistry, get_hook_registry, Hooks
from .interfaces import (
    PluginContext,
    PluginMetadata,
    SettingsAPI,
    CamerasAPI,
    FramesAPI,
    UIAPI,
    FilesAPI,
    NotificationsAPI,
    LoggerAPI,
    TimersAPI,
)

# Re-exportar el sistema de extensiones
from core.extension_registry import (
    ExtensionRegistry,
    get_extension_registry,
    set_extension_registry,
)
from core.event_bus import EventBus, get_event_bus, set_event_bus
from core.events import (
    CAMERA_ADDED, CAMERA_REMOVED, CAMERA_CONNECTED, CAMERA_DISCONNECTED,
    CAMERA_ERROR,
    FRAME_READY, FRAME_ANALYZED,
    MOTION_DETECTED, FACE_DETECTED, OBJECT_DETECTED, TEXT_RECOGNIZED,
    IMAGE_CAPTURED, IMAGE_SAVED,
    RECORDING_STARTED, RECORDING_STOPPED, VIDEO_SAVED,
    SETTINGS_CHANGED, PLUGIN_ENABLED, PLUGIN_DISABLED,
    APP_STARTING, APP_STARTED, APP_CLOSING, APP_CLOSED,
)
from core.extensions.interfaces import (
    # Cámaras
    CameraProvider,
    CameraDetector,
    CameraLifecycleListener,
    # Frames
    FramePreProcessor,
    FramePostProcessor,
    FrameAnalyzer,
    # UI
    ToolbarProvider,
    MenuProvider,
    ConfigTab,
    ConfigSection,
    ConfigWidget,
    VideoOverlay,
    StatusWidget,
    DialogProvider,
    UIExtension,
    # Comportamiento
    KeyboardInterceptor,
    MouseInterceptor,
    AppLifecycleHook,
    StartupHook,
    ShutdownHook,
    # Temas
    ThemeProvider,
    IconProvider,
    # Datos
    FileHandler,
    StorageProvider,
    ImportProvider,
    ExportProvider,
    # Plugins (meta)
    PluginWrapper,
    PluginLifecycleHook,
    PluginValidator,
    # Utilidades
    NotificationProvider,
    TaskScheduler,
)

from core.extensions.types import (
    Priority,
    CameraProtocol,
    FrameFormat,
    NotificationLevel,
    ThemeMode,
    Capability,
)

__all__ = [
    # Plugin API
    "PluginManager",
    "BasePlugin",
    "PluginContext",
    "get_plugin_manager",
    "set_plugin_manager",
    "PluginError",
    "PluginNotFoundError",
    "PluginDependencyError",
    "PluginLoadError",
    "HookRegistry",
    "get_hook_registry",
    "Hooks",
    "PluginMetadata",
    "SettingsAPI",
    "CamerasAPI",
    "FramesAPI",
    "UIAPI",
    "FilesAPI",
    "NotificationsAPI",
    "LoggerAPI",
    "TimersAPI",

    # Extensiones
    "ExtensionRegistry",
    "get_extension_registry",
    "set_extension_registry",

    # Event bus
    "EventBus",
    "get_event_bus",
    "set_event_bus",

    # Nombres de eventos
    "CAMERA_ADDED", "CAMERA_REMOVED", "CAMERA_CONNECTED",
    "CAMERA_DISCONNECTED", "CAMERA_ERROR",
    "FRAME_READY", "FRAME_ANALYZED",
    "MOTION_DETECTED", "FACE_DETECTED", "OBJECT_DETECTED",
    "TEXT_RECOGNIZED",
    "IMAGE_CAPTURED", "IMAGE_SAVED",
    "RECORDING_STARTED", "RECORDING_STOPPED", "VIDEO_SAVED",
    "SETTINGS_CHANGED", "PLUGIN_ENABLED", "PLUGIN_DISABLED",
    "APP_STARTING", "APP_STARTED", "APP_CLOSING", "APP_CLOSED",

    # Interfaces de extensión
    "CameraProvider",
    "CameraDetector",
    "CameraLifecycleListener",
    "FramePreProcessor",
    "FramePostProcessor",
    "FrameAnalyzer",
    "ToolbarProvider",
    "MenuProvider",
    "ConfigTab",
    "ConfigSection",
    "ConfigWidget",
    "VideoOverlay",
    "StatusWidget",
    "DialogProvider",
    "UIExtension",
    "KeyboardInterceptor",
    "MouseInterceptor",
    "AppLifecycleHook",
    "StartupHook",
    "ShutdownHook",
    "ThemeProvider",
    "IconProvider",
    "FileHandler",
    "StorageProvider",
    "ImportProvider",
    "ExportProvider",
    "PluginWrapper",
    "PluginLifecycleHook",
    "PluginValidator",
    "NotificationProvider",
    "TaskScheduler",

    # Tipos
    "Priority",
    "CameraProtocol",
    "FrameFormat",
    "NotificationLevel",
    "ThemeMode",
    "Capability",
]