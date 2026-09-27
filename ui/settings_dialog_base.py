"""
Base para pestañas de configuración de plugins.

Soporta DOS patrones:
  1. NUEVO (recomendado): usar stage_advanced/stage_detection en apply_changes()
     para acumular cambios. SettingsDialog los aplica en batch.
  2. LEGACY: sobrescribir apply_changes() y escribir directamente a QSettings.
     Se detecta automáticamente si el tab NO usó stage_*.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from typing import Dict, Any

from utils.logger import get_logger

logger = get_logger("PluginConfigTab")


class PluginConfigTab(QWidget):
    """Base para tabs de configuración de plugins."""

    def __init__(self, plugin_name: str, context, parent=None):
        super().__init__(parent)
        self.plugin_name = plugin_name
        self.context = context
        self._config: Dict[str, Any] = {}

        # Buffers para cambios staged
        self._staged_advanced: Dict[str, Any] = {}
        self._staged_detection: Dict[str, Any] = {}
        self._staged_plugin_config: Dict[str, Any] = {}

        # Flag para detectar si el tab usó el nuevo patrón
        self._used_staging: bool = False

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

        header = QLabel(f"Configuración de: {self.plugin_name}")
        header.setStyleSheet(
            "font-size: 15px; font-weight: bold; color: #4da0c4;"
        )
        self.layout.addWidget(header)

        self.build_ui()
        self.layout.addStretch()

    def build_ui(self):
        label = QLabel("Este plugin no tiene configuración.")
        label.setStyleSheet("color: #888; font-style: italic;")
        self.layout.addWidget(label)

    # ==================== STAGING ====================

    def stage_advanced(self, key: str, value: Any):
        self._staged_advanced[key] = value
        self._used_staging = True

    def stage_advanced_batch(self, values: Dict[str, Any]):
        self._staged_advanced.update(values)
        self._used_staging = True

    def stage_detection(self, key: str, value: Any):
        self._staged_detection[key] = value
        self._used_staging = True

    def stage_detection_batch(self, values: Dict[str, Any]):
        self._staged_detection.update(values)
        self._used_staging = True

    def stage_plugin_config(self, key: str, value: Any):
        self._staged_plugin_config[key] = value
        self._used_staging = True

    def get_staged_changes(self) -> dict:
        return {
            "advanced": dict(self._staged_advanced),
            "detection": dict(self._staged_detection),
            "plugin_config": dict(self._staged_plugin_config),
        }

    def has_staged_changes(self) -> bool:
        return bool(
            self._staged_advanced
            or self._staged_detection
            or self._staged_plugin_config
        )

    # ==================== API ====================

    def get_config(self) -> Dict[str, Any]:
        return dict(self._config)

    def set_config(self, config: Dict[str, Any]):
        self._config = dict(config)

    def apply_changes(self) -> bool:
        """
        Por defecto: no hacer nada.
        Los tabs que usen stage_* no necesitan sobrescribir esto.
        Los tabs legacy pueden sobrescribir para escribir directo.
        """
        return True

    # ==================== ALIAS LEGACY ====================

    def on_save(self) -> bool:
        """Alias de apply_changes para compatibilidad."""
        return self.apply_changes()