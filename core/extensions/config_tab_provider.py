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
            priority=100,   # ← mayor = más a la derecha
        ),
    )
"""
from typing import Type, Optional
from PySide6.QtWidgets import QWidget

from utils.logger import get_logger

logger = get_logger("PluginConfigTabProvider")


class PluginConfigTabProvider:
    """Envuelve un PluginConfigTab para exponerlo como ConfigTab (on-demand)."""

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

    def on_save(self) -> bool:
        if self._widget is not None and hasattr(self._widget, 'apply_changes'):
            try:
                return self._widget.apply_changes()
            except Exception as e:
                logger.error(f"❌ Error guardando '{self._tab_id}': {e}")
                return False
        return True

    def on_load(self):
        pass

    def cleanup(self):
        """Libera el widget si está instanciado."""
        if self._widget is not None:
            try:
                self._widget.setParent(None)
                self._widget.deleteLater()
            except Exception:
                pass
            self._widget = None