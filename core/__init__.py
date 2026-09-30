"""
ProCamera Core.

Núcleo autosuficiente del sistema. NO importa de `plugins/`.

Submódulos principales:
  - core.event_bus             EventBus genérico
  - core.events                Nombres de eventos del dominio
  - core.extension_registry    Registry de extensiones
  - core.extensions            Puntos de extensión (interfaces, types, ...)
  - core.plugin_api            API de plugins (BasePlugin, PluginManager, ...)
  - core.engine                Motores de captura
  - core.models                Modelos de datos (CameraDevice, ...)
  - core.settings_manager      Persistencia de configuración
  - core.file_manager          Guardado de archivos

IMPORTANTE: Este paquete NO debe exponer símbolos en `__init__.py` porque
cada submódulo tiene su propia inicialización y añadir imports aquí puede
crear ciclos (por ejemplo, core.settings_manager <-> core.plugin_api).
"""

__version__ = "2.0.0"
__all__ = []