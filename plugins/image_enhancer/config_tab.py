"""
Tab de configuración del plugin image_enhancer.

NOTA: ImageEnhancer no tiene parámetros globales en advanced_config,
porque sus ajustes se aplican por-llamada desde el diálogo.
Esta tab muestra los presets disponibles y permite configurar
el preset por defecto + auto-mejora.
"""
from PySide6.QtWidgets import (
    QVBoxLayout, QGridLayout, QGroupBox, QLabel,
    QComboBox, QCheckBox, QScrollArea, QWidget
)

from ui.settings.settings_dialog_base import PluginConfigTab


class ImageEnhancerConfigTab(PluginConfigTab):
    """Configuración del plugin image_enhancer."""

    SCHEMA = {
        "image_enhancer_default_preset": {"type": "str", "default": "auto"},
        "image_enhancer_auto_on_capture": {"type": "bool", "default": False},
        "image_enhancer_auto_on_scan": {"type": "bool", "default": True},
    }

    def build_ui(self):
        if self.context.settings is not None:
            self.context.settings.register_config_schema(
                self.plugin_name, self.SCHEMA
            )

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)

        # ============ Grupo 1: Preset por defecto ============
        preset_group = QGroupBox("🎯 Preset por defecto")
        preset_layout = QGridLayout(preset_group)
        preset_layout.setVerticalSpacing(10)
        preset_layout.setHorizontalSpacing(20)

        preset_layout.addWidget(QLabel("Preset:"), 0, 0)
        self.preset_combo = QComboBox()
        self.preset_combo.addItems([
            "auto", "documento", "foto", "noche",
            "retrato", "paisaje", "ninguno"
        ])
        preset_layout.addWidget(self.preset_combo, 0, 1)

        layout.addWidget(preset_group)

        # ============ Grupo 2: Automatización ============
        auto_group = QGroupBox("🤖 Automatización")
        auto_layout = QVBoxLayout(auto_group)

        self.auto_capture_cb = QCheckBox(
            "Aplicar mejora automática al capturar"
        )
        auto_layout.addWidget(self.auto_capture_cb)

        self.auto_scan_cb = QCheckBox(
            "Aplicar mejora automática al escanear documentos"
        )
        auto_layout.addWidget(self.auto_scan_cb)

        layout.addWidget(auto_group)

        # ============ Grupo 3: Info ============
        info_group = QGroupBox("ℹ️ Info")
        info_layout = QVBoxLayout(info_group)

        info_text = QLabel(
            "💡 Los controles finos (brillo, contraste, gamma, etc.) "
            "se ajustan por-imagen desde el diálogo de edición.\n\n"
            "Los presets se aplican con un solo clic desde el editor."
        )
        info_text.setStyleSheet("color: rgba(255,255,255,0.6); font-size: 11px;")
        info_text.setWordWrap(True)
        info_layout.addWidget(info_text)

        layout.addWidget(info_group)
        layout.addStretch()

        scroll.setWidget(content)
        self.layout.addWidget(scroll)

        self._load_values()

    def _load_values(self):
        try:
            self.preset_combo.setCurrentText(
                self._config.get("image_enhancer_default_preset", "auto")
            )
            self.auto_capture_cb.setChecked(
                self._config.get("image_enhancer_auto_on_capture", False)
            )
            self.auto_scan_cb.setChecked(
                self._config.get("image_enhancer_auto_on_scan", True)
            )
        except Exception as e:
            print(f"Error cargando valores: {e}")

    def get_config(self):
        return {
            "image_enhancer_default_preset": self.preset_combo.currentText(),
            "image_enhancer_auto_on_capture": self.auto_capture_cb.isChecked(),
            "image_enhancer_auto_on_scan": self.auto_scan_cb.isChecked(),
        }

    def apply_changes(self) -> bool:
        try:
            return self.context.settings.set_plugin_config(
                self.plugin_name, self.get_config()
            )
        except Exception as e:
            print(f"Error aplicando config: {e}")
            return False