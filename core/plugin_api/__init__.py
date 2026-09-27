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

# ✅ Re-exportar el sistema de extensiones
from core.extension_registry import (
    ExtensionRegistry,
    get_extension_registry,
    set_extension_registry,
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
    # Plugins
    PluginWrapper,
    PluginLifecycleHook,
    PluginValidator,
    # Utilidades
    Logger,
    NotificationProvider,
    TaskScheduler,
    # ✅ UI genérica
    UIExtension,
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
    # ... (lo de antes) ...
    "PluginManager", "BasePlugin", "PluginContext",

    # Extensiones
    "ExtensionRegistry",
    "get_extension_registry",
    "set_extension_registry",

    # Interfaces de extensión
    "CameraProvider", "CameraDetector", "CameraLifecycleListener",
    "FramePreProcessor", "FramePostProcessor", "FrameAnalyzer",
    "ToolbarProvider", "MenuProvider", "ConfigTab", "ConfigSection",
    "ConfigWidget", "VideoOverlay", "StatusWidget", "DialogProvider",
    "KeyboardInterceptor", "MouseInterceptor",
    "AppLifecycleHook", "StartupHook", "ShutdownHook",
    "ThemeProvider", "IconProvider",
    "FileHandler", "StorageProvider", "ImportProvider", "ExportProvider",
    "PluginWrapper", "PluginLifecycleHook", "PluginValidator",
    "Logger", "NotificationProvider", "TaskScheduler",
    "UIExtension",

    # Tipos
    "Priority", "CameraProtocol", "FrameFormat",
    "NotificationLevel", "ThemeMode", "Capability",
]