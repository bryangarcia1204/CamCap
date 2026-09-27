"""
Registro de factories de ConfigWidget.

Los plugins pueden registrar TIPOS de widgets de config
(color picker, file picker, etc.) que luego se usan en
los diálogos de configuración.

Uso:
    registry = get_config_widget_registry()
    registry.register("color", lambda key, default, **kw: ColorPicker(key, default))
    widget = registry.create("color", "bg_color", "#000000")
"""
import threading
from typing import Dict, Callable, Any, Optional

from utils.logger import get_logger

logger = get_logger("ConfigWidgetRegistry")


class ConfigWidgetRegistry:
    """Registry de factories de ConfigWidget."""

    def __init__(self):
        self._factories: Dict[str, Callable] = {}
        self._lock = threading.RLock()
        logger.info("📦 ConfigWidgetRegistry inicializado")

    def register(self, type_name: str, factory: Callable, owner: str = ""):
        """
        Registra un factory.

        Args:
            type_name: nombre del tipo (ej. "color", "file", "slider")
            factory: callable(key, default, **kwargs) -> ConfigWidget
            owner: quién lo registra
        """
        if not callable(factory):
            logger.error(f"❌ factory no es callable para '{type_name}'")
            return

        with self._lock:
            self._factories[type_name] = factory

        logger.debug(
            f"📦 [config_widget] '{type_name}' ← {owner or 'anonymous'}"
        )

    def create(
        self, type_name: str, key: str, default: Any = None, **kwargs
    ) -> Optional[Any]:
        """
        Crea un ConfigWidget.

        Returns:
            Instancia del ConfigWidget, o None si el tipo no está registrado.
        """
        with self._lock:
            factory = self._factories.get(type_name)

        if factory is None:
            logger.debug(f"⚠️ [config_widget] Tipo '{type_name}' no registrado")
            return None

        try:
            return factory(key, default, **kwargs)
        except Exception as e:
            logger.error(
                f"❌ [config_widget] Error creando '{type_name}': {e}",
                exc_info=True,
            )
            return None

    def list_types(self) -> list:
        with self._lock:
            return list(self._factories.keys())

    def has(self, type_name: str) -> bool:
        with self._lock:
            return type_name in self._factories

    def clear(self):
        with self._lock:
            self._factories.clear()


# ==================== SINGLETON ====================

_registry: Optional[ConfigWidgetRegistry] = None
_lock = threading.Lock()


def get_config_widget_registry() -> ConfigWidgetRegistry:
    global _registry
    with _lock:
        if _registry is None:
            _registry = ConfigWidgetRegistry()
    return _registry


def set_config_widget_registry(registry: ConfigWidgetRegistry):
    global _registry
    with _lock:
        _registry = registry