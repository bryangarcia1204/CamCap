"""
Tab de configuración del plugin debug_console.
"""
from PySide6.QtWidgets import (
    QVBoxLayout, QFormLayout, QSpinBox, QCheckBox, QLabel
)

from ui.settings_dialog_base import PluginConfigTab


class DebugConsoleConfigTab(PluginConfigTab):
    """Configuración del plugin de consola."""

    def build_ui(self):
        form = QFormLayout()

        # Máximo de líneas
        self.max_lines_spin = QSpinBox()
        self.max_lines_spin.setRange(100, 50000)
        self.max_lines_spin.setValue(
            self._config.get("max_lines", 5000)
        )
        self.max_lines_spin.setSingleStep(500)
        form.addRow("Máximo de líneas:", self.max_lines_spin)

        # Auto-scroll
        self.autoscroll_cb = QCheckBox("Auto-scroll al final")
        self.autoscroll_cb.setChecked(
            self._config.get("auto_scroll", True)
        )
        form.addRow("", self.autoscroll_cb)

        # Info
        info = QLabel(
            "💡 La consola se togglea con Ctrl+Alt+C x3"
        )
        info.setStyleSheet("color: #888; font-size: 11px; font-style: italic;")
        form.addRow("", info)

        self.layout.addLayout(form)

    def get_config(self):
        return {
            "max_lines": self.max_lines_spin.value(),
            "auto_scroll": self.autoscroll_cb.isChecked(),
        }