"""
Decoradores útiles para registrar extensiones automáticamente.

Uso:
    @frame_processor(priority=Priority.HIGH)
    class MyProcessor:
        def process(self, camera_id, frame):
            return frame
        def get_priority(self):
            return 10

    # El decorador registra la clase en el registry global
"""
from typing import Type, Any
from utils.logger import get_logger

logger = get_logger("Extensions.Decorators")


def extension(interface: Type, priority: int = 50, owner: str = ""):
    """
    Decorador genérico para registrar una clase como implementación
    de una interfaz.

    Uso:
        @extension(CameraProvider, priority=10)
        class MyCameraProvider:
            ...
    """
    def decorator(cls):
        from core.extension_registry import get_extension_registry
        registry = get_extension_registry()
        try:
            instance = cls()
            registry.register(interface, instance, priority=priority, owner=owner)
            logger.debug(
                f"📦 Decorador registró {cls.__name__} para {interface.__name__}"
            )
        except Exception as e:
            logger.error(
                f"❌ Error registrando {cls.__name__}: {e}",
                exc_info=True,
            )
        return cls
    return decorator


def frame_processor(priority: int = 50, owner: str = ""):
    """Registra como FramePreProcessor."""
    from .interfaces import FramePreProcessor
    return extension(FramePreProcessor, priority=priority, owner=owner)


def camera_provider(priority: int = 50, owner: str = ""):
    """Registra como CameraProvider."""
    from .interfaces import CameraProvider
    return extension(CameraProvider, priority=priority, owner=owner)


def config_tab(priority: int = 50, owner: str = ""):
    """Registra como ConfigTab."""
    from .interfaces import ConfigTab
    return extension(ConfigTab, priority=priority, owner=owner)


def theme_provider(priority: int = 50, owner: str = ""):
    """Registra como ThemeProvider."""
    from .interfaces import ThemeProvider
    return extension(ThemeProvider, priority=priority, owner=owner)