"""
Base para pestañas de configuración de plugins.

Los plugins pueden heredar de `PluginConfigTab` para crear
su propia pestaña de configuración.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
)
from PySide6.QtCore import Qt
from typing import Dict, Any, Callable, Optional

from utils.logger import get_logger

logger = get_logger("PluginConfigTab")


class PluginConfigTab(QWidget):
    """
    Base para tabs de configuración de plugins.

    Los plugins pueden:
    - Sobrescribir `build_ui()` para crear sus widgets
    - Usar `get_config()` / `set_config()` para leer/escribir
    - Usar `apply_changes()` para persistir cambios
    """

    def __init__(self, plugin_name: str, context, parent=None):
        super().__init__(parent)
        self.plugin_name = plugin_name
        self.context = context
        self._config: Dict[str, Any] = {}

        # Cargar config actual
        if context.settings is not None:
            try:
                self._config = context.settings.get_plugin_config(plugin_name)
            except Exception as e:
                logger.error(f"Error cargando config de '{plugin_name}': {e}")
                self._config = {}

        self._setup_base_ui()

    def _setup_base_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(16, 16, 16, 16)
        self.layout.setSpacing(12)

        # Header
        header = QLabel(f"Configuración de: {self.plugin_name}")
        header.setStyleSheet(
            "font-size: 15px; font-weight: bold; color: #4da0c4;"
        )
        self.layout.addWidget(header)

        # Contenido (subclases sobrescriben)
        self.build_ui()

        self.layout.addStretch()

    def build_ui(self):
        """Sobrescribir para añadir widgets."""
        label = QLabel("Este plugin no tiene configuración.")
        label.setStyleSheet("color: #888; font-style: italic;")
        self.layout.addWidget(label)

    def get_config(self) -> Dict[str, Any]:
        """Retorna la config actual del tab."""
        return dict(self._config)

    def set_config(self, config: Dict[str, Any]):
        """Establece la config del tab."""
        self._config = dict(config)

    def apply_changes(self) -> bool:
        """
        Aplica los cambios al QSettings.
        Llamado por SettingsDialog al guardar.
        """
        if self.context.settings is None:
            return False

        try:
            success = self.context.settings.set_plugin_config(
                self.plugin_name,
                self._config,
            )
            if success:
                logger.info(f"✅ Config de '{self.plugin_name}' aplicada")
            return success
        except Exception as e:
            logger.error(f"❌ Error aplicando config: {e}")
            return False