"""
Tab de configuración del plugin debug_console.

Usa el patrón de staging moderno:
  - apply_changes() NO escribe en QSettings, solo stagea.
  - SettingsDialog aplica todo en batch al guardar.
"""
from PySide6.QtWidgets import (
    QFormLayout, QSpinBox, QCheckBox, QLabel,
)

from ui.settings_dialog_base import PluginConfigTab
from utils.logger import get_logger

logger = get_logger("Plugin.DebugConsole.ConfigTab")


class DebugConsoleConfigTab(PluginConfigTab):
    """Configuración del plugin de consola."""

    SCHEMA = {
        "max_lines": {"type": "int", "default": 5000},
        "auto_scroll": {"type": "bool", "default": True},
    }

    def build_ui(self):
        # Registrar schema para tipado en QSettings
        if self.context.settings is not None:
            self.context.settings.register_config_schema(
                self.plugin_name, self.SCHEMA
            )

        form = QFormLayout()

        # Máximo de líneas
        self.max_lines_spin = QSpinBox()
        self.max_lines_spin.setRange(100, 50000)
        self.max_lines_spin.setSingleStep(500)
        self.max_lines_spin.setValue(
            int(self._config.get("max_lines", 5000))
        )
        self.max_lines_spin.setToolTip(
            "Número máximo de líneas que se mantienen en la consola.\n"
            "Al superarlo, se eliminan las más antiguas."
        )
        form.addRow("Máximo de líneas:", self.max_lines_spin)

        # Auto-scroll
        self.autoscroll_cb = QCheckBox("Auto-scroll al final")
        self.autoscroll_cb.setChecked(
            bool(self._config.get("auto_scroll", True))
        )
        self.autoscroll_cb.setToolTip(
            "Si está activo, la consola baja automáticamente\n"
            "al llegar logs nuevos."
        )
        form.addRow("", self.autoscroll_cb)

        # Separador visual
        sep = QLabel("")
        sep.setFixedHeight(8)
        form.addRow("", sep)

        # Info
        info = QLabel(
            "💡 La consola se togglea con <b>Ctrl+Alt+C × 3</b>"
        )
        info.setStyleSheet(
            "color: rgba(255,255,255,0.6); "
            "font-size: 11px; font-style: italic;"
        )
        info.setWordWrap(True)
        form.addRow("", info)

        self.layout.addLayout(form)

    # ==================== API ====================

    def get_config(self) -> dict:
        return {
            "max_lines": int(self.max_lines_spin.value()),
            "auto_scroll": bool(self.autoscroll_cb.isChecked()),
        }

    def apply_changes(self) -> bool:
        """
        Stagea los cambios. El SettingsDialog los aplica en batch.
        """
        try:
            config = self.get_config()

            # Stagear para que SettingsDialog los persista
            for key, value in config.items():
                self.stage_plugin_config(key, value)

            # Aplicar en vivo al plugin (sin esperar al save)
            try:
                from core.plugin_api import get_plugin_manager
                pm = get_plugin_manager()
                if pm is not None:
                    plugin = pm.get(self.plugin_name)
                    if plugin is not None and hasattr(plugin, "apply_config"):
                        plugin.apply_config(config)
            except Exception as e:
                logger.debug(f"No se pudo aplicar config en vivo: {e}")

            return True
        except Exception as e:
            logger.error(f"Error aplicando config: {e}", exc_info=True)
            return False