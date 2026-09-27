"""
Wrapper genérico para exponer un PluginConfigTab como ConfigTab.

Resuelve el problema de que QWidget no se puede instanciar sin QApplication.

Uso en plugin.py:
    from core.extensions.config_tab_provider import PluginConfigTabProvider
    from plugins.motion_detector.config_tab import MotionDetectorConfigTab

    self.register_extension(
        ConfigTab,
        PluginConfigTabProvider(
            plugin_name=self.NAME,
            plugin_context=self.context,
            tab_class=MotionDetectorConfigTab,
            tab_id="plugin_motion_detector",
            title="Motion Detector",
            icon="🚶",
        ),
    )
"""
from typing import Type, Optional
from PySide6.QtWidgets import QWidget

from utils.logger import get_logger

logger = get_logger("PluginConfigTabProvider")


class PluginConfigTabProvider:
    """
    Envuelve un PluginConfigTab para exponerlo como ConfigTab (on-demand).

    Delega TODOS los métodos relevantes al widget instanciado, incluyendo
    el nuevo sistema de staging.
    """

    def __init__(
        self,
        plugin_name: str,
        plugin_context,
        tab_class: Type,
        tab_id: str,
        title: str,
        icon: str = "",
    ):
        self._plugin_name = plugin_name
        self._plugin_context = plugin_context
        self._tab_class = tab_class
        self._tab_id = tab_id
        self._title = title
        self._icon = icon
        self._widget: Optional[QWidget] = None

    def get_id(self) -> str:
        return self._tab_id

    def get_title(self) -> str:
        return self._title

    def get_icon(self) -> str:
        return self._icon

    def get_widget(self) -> Optional[QWidget]:
        if self._widget is None:
            try:
                self._widget = self._tab_class(
                    self._plugin_name,
                    self._plugin_context,
                )
                logger.debug(f"🎨 ConfigTab '{self._tab_id}' instanciada")
            except Exception as e:
                logger.error(
                    f"❌ Error instanciando ConfigTab '{self._tab_id}': {e}",
                    exc_info=True,
                )
                return None
        return self._widget

    # ==================== DELEGACIÓN AL WIDGET ====================

    def apply_changes(self) -> bool:
        """Delega al widget si existe."""
        if self._widget is not None and hasattr(self._widget, "apply_changes"):
            try:
                return self._widget.apply_changes()
            except Exception as e:
                logger.error(f"❌ Error en apply_changes de '{self._tab_id}': {e}", exc_info=True)
                return False
        return True

    def on_save(self) -> bool:
        """Alias legacy."""
        return self.apply_changes()

    def on_load(self):
        """Carga inicial (opcional)."""
        if self._widget is not None and hasattr(self._widget, "on_load"):
            try:
                self._widget.on_load()
            except Exception as e:
                logger.debug(f"Error en on_load de '{self._tab_id}': {e}")

    # ✅ NUEVO: delegación de staging
    def get_staged_changes(self) -> dict:
        """Delega al widget. Retorna {} si el widget no usa staging."""
        if self._widget is not None and hasattr(self._widget, "get_staged_changes"):
            try:
                return self._widget.get_staged_changes()
            except Exception as e:
                logger.error(
                    f"❌ Error en get_staged_changes de '{self._tab_id}': {e}",
                    exc_info=True,
                )
                return {"advanced": {}, "detection": {}, "plugin_config": {}}
        return {"advanced": {}, "detection": {}, "plugin_config": {}}

    def has_staged_changes(self) -> bool:
        """Delega al widget."""
        if self._widget is not None and hasattr(self._widget, "has_staged_changes"):
            try:
                return self._widget.has_staged_changes()
            except Exception:
                return False
        return False

    def get_config(self) -> dict:
        """Delega al widget."""
        if self._widget is not None and hasattr(self._widget, "get_config"):
            try:
                return self._widget.get_config()
            except Exception:
                return {}
        return {}

    # ==================== CLEANUP ====================

    def cleanup(self):
        """Libera el widget si está instanciado."""
        if self._widget is not None:
            try:
                self._widget.setParent(None)
                self._widget.deleteLater()
            except Exception:
                pass
            self._widget = None