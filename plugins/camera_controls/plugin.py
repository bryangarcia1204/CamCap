"""
Plugin: Camera Controls

Añade botones de control de hardware de cámara IP (flash).
El flash es una capacidad NATIVA de la cámara (endpoint HTTP),
no del detector de movimiento.

Capabilities:
  - camera_control: controlar hardware de la cámara (flash)
"""
from core.plugin_api import BasePlugin
from core.extensions.interfaces import UIExtension


class CameraControlsPlugin(BasePlugin):
    NAME = "camera_controls"
    VERSION = "1.0.0"
    DESCRIPTION = "Controla hardware de cámara IP (flash, etc.)"
    AUTHOR = "ProCamera"
    DEPENDENCIES = []
    REQUIRES_DEBUG = False

    def on_load(self) -> bool:
        self.logger.info("🔦 CameraControls cargado")
        return True

    def on_enable(self) -> bool:
        try:
            self.register_extension(
                UIExtension,
                _FlashUIExtension(self),
                priority=100,   # antes que audio (110)
            )
            self.logger.info("✅ CameraControls activado (flash)")
            return True
        except Exception as e:
            self.logger.error(f"❌ Error activando: {e}", exc_info=True)
            return False

    def on_disable(self):
        self.logger.info("⏸️ CameraControls desactivado")

    def on_unload(self):
        self.logger.info("🔌 CameraControls descargado")


class _FlashUIExtension:
    """Inyecta botones flash y auto-flash en el header de cada cámara IP."""

    def __init__(self, plugin: CameraControlsPlugin):
        self._plugin = plugin

    def get_id(self) -> str:
        return "camera_controls.flash"

    def get_target(self) -> str:
        return "camera_widget"

    def get_slot(self) -> str:
        return "header"

    def get_priority(self) -> int:
        return 100

    def get_widgets(self, context: dict):
        from plugins.camera_controls.widgets import create_flash_widgets

        camera = context.get("camera")
        camera_widget = context.get("widget")
        camera_id = context.get("camera_id")

        if camera is None or camera_widget is None:
            return []

        return create_flash_widgets(camera_id, camera, camera_widget)