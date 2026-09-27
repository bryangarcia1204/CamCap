"""
Sistema de extensiones de ProCamera.

El Core expone puntos de extensión GENÉRICOS. Cualquier código
(plugins o builtin) puede extender el comportamiento sin modificar
el Core.
"""
from .interfaces import (
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

from .types import (
    CameraProtocol,
    FrameFormat,
    Priority,
    NotificationLevel,
    ThemeMode,
    Capability,
)

from .capability_checker import (
    CapabilityChecker,
    get_capability_checker,
    set_capability_checker,
)

from .services import CoreServices, get_core_services, set_core_services
from .decorators import (
    extension,
    frame_processor,
    camera_provider,
    config_tab,
    theme_provider,
)

from .sandbox import (
    SandboxHook,
    get_sandbox_hook,
    activate_sandbox,
)

__all__ = [
    # Cámaras
    "CameraProvider",
    "CameraDetector",
    "CameraLifecycleListener",

    # Frames
    "FramePreProcessor",
    "FramePostProcessor",
    "FrameAnalyzer",

    # UI
    "ToolbarProvider",
    "MenuProvider",
    "ConfigTab",
    "ConfigSection",
    "ConfigWidget",
    "VideoOverlay",
    "StatusWidget",
    "DialogProvider",
    "UIExtension",

    # Comportamiento
    "KeyboardInterceptor",
    "MouseInterceptor",
    "AppLifecycleHook",
    "StartupHook",
    "ShutdownHook",
    "SandboxHook",
    "get_sandbox_hook",
    "activate_sandbox",

    # Temas
    "ThemeProvider",
    "IconProvider",

    # Datos
    "FileHandler",
    "StorageProvider",
    "ImportProvider",
    "ExportProvider",

    # Plugins (meta)
    "PluginWrapper",
    "PluginLifecycleHook",
    "PluginValidator",
    "CapabilityChecker",
    "get_capability_checker",
    "set_capability_checker",

    # Utilidades
    "NotificationProvider",
    "TaskScheduler",

    # Tipos
    "CameraProtocol",
    "FrameFormat",
    "Priority",
    "NotificationLevel",
    "ThemeMode",
    "Capability",

    # Servicios
    "CoreServices",
    "get_core_services",
    "set_core_services",

    # Decoradores
    "extension",
    "frame_processor",
    "camera_provider",
    "config_tab",
    "theme_provider",
]