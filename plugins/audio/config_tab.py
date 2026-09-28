"""
Tab de configuración del plugin audio.

Incluye TODOS los parámetros de audio:
- Sample rate, canales, volumen
- Endpoints
- Buffers de grabación (blocksize, max_buffer)
"""
from PySide6.QtWidgets import (
    QVBoxLayout, QGridLayout, QGroupBox, QLabel,
    QComboBox, QCheckBox, QDoubleSpinBox, QLineEdit, QSpinBox,
    QScrollArea, QWidget
)
from PySide6.QtCore import Qt

from ui.settings.settings_dialog_base import PluginConfigTab


class AudioConfigTab(PluginConfigTab):
    """Configuración completa del audio."""

    SCHEMA = {
        "audio_sample_rate": {"type": "int", "default": 44100},
        "audio_channels": {"type": "int", "default": 1},
        "audio_volume": {"type": "float", "default": 0.7},
        "audio_detect_endpoint": {"type": "bool", "default": True},
        "audio_endpoints_priority": {"type": "str", "default": "wav,pcm"},
        "audio_blocksize": {"type": "int", "default": 1024},
        "audio_max_buffer_seconds": {"type": "float", "default": 2.0},
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

        # ============ Formato ============
        format_group = QGroupBox("🎵 Formato de Audio")
        format_layout = QGridLayout(format_group)
        format_layout.setVerticalSpacing(10)
        format_layout.setHorizontalSpacing(20)

        format_layout.addWidget(QLabel("Sample rate:"), 0, 0)
        self.sample_rate_combo = QComboBox()
        self.sample_rate_combo.addItems([
            "8000", "16000", "22050", "44100", "48000"
        ])
        format_layout.addWidget(self.sample_rate_combo, 0, 1)

        format_layout.addWidget(QLabel("Canales:"), 1, 0)
        self.channels_combo = QComboBox()
        self.channels_combo.addItems(["Mono (1)", "Estéreo (2)"])
        format_layout.addWidget(self.channels_combo, 1, 1)

        format_layout.addWidget(QLabel("Volumen inicial:"), 2, 0)
        self.volume_spin = QDoubleSpinBox()
        self.volume_spin.setRange(0.0, 1.0)
        self.volume_spin.setSingleStep(0.05)
        self.volume_spin.setDecimals(2)
        format_layout.addWidget(self.volume_spin, 2, 1)

        layout.addWidget(format_group)

        # ============ Endpoints ============
        endpoint_group = QGroupBox("🌐 Endpoints")
        endpoint_layout = QVBoxLayout(endpoint_group)

        self.detect_endpoint_cb = QCheckBox("Auto-detectar endpoint de audio")
        endpoint_layout.addWidget(self.detect_endpoint_cb)

        endpoint_layout.addWidget(QLabel("Prioridad de endpoints:"))
        self.priority_edit = QLineEdit()
        self.priority_edit.setPlaceholderText("wav,pcm")
        endpoint_layout.addWidget(self.priority_edit)

        info_label = QLabel(
            "💡 Los endpoints se prueban en orden. El primero que "
            "responda 200 OK será usado."
        )
        info_label.setStyleSheet("color: rgba(255,255,255,0.6); font-size: 11px;")
        info_label.setWordWrap(True)
        endpoint_layout.addWidget(info_label)

        layout.addWidget(endpoint_group)

        # ============ Grabación de audio ============
        rec_group = QGroupBox("🎬 Grabación con audio")
        rec_layout = QGridLayout(rec_group)
        rec_layout.setVerticalSpacing(10)
        rec_layout.setHorizontalSpacing(20)

        rec_layout.addWidget(QLabel("Audio blocksize:"), 0, 0)
        self.blocksize_spin = QSpinBox()
        self.blocksize_spin.setRange(256, 4096)
        self.blocksize_spin.setSingleStep(128)
        rec_layout.addWidget(self.blocksize_spin, 0, 1)

        rec_layout.addWidget(QLabel("Buffer máximo (s):"), 1, 0)
        self.max_buffer_spin = QDoubleSpinBox()
        self.max_buffer_spin.setRange(0.5, 10.0)
        self.max_buffer_spin.setSingleStep(0.5)
        self.max_buffer_spin.setDecimals(1)
        self.max_buffer_spin.setSuffix(" s")
        rec_layout.addWidget(self.max_buffer_spin, 1, 1)

        layout.addWidget(rec_group)

        # ============ Info ============
        info_group = QGroupBox("ℹ️ Info")
        info_layout = QVBoxLayout(info_group)

        info_text = QLabel(
            "💡 El mute se activa desde el botón 🔇 en cada cámara.\n"
            "El volumen se ajusta por cámara en runtime."
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
            from utils.config_loader import advanced_config
            cfg = advanced_config.get_all()

            self.sample_rate_combo.setCurrentText(
                str(cfg.get("audio_sample_rate", 44100))
            )
            channels = cfg.get("audio_channels", 1)
            self.channels_combo.setCurrentIndex(0 if channels == 1 else 1)
            self.volume_spin.setValue(cfg.get("audio_volume", 0.7))
            self.detect_endpoint_cb.setChecked(cfg.get("audio_detect_endpoint", True))
            self.priority_edit.setText(cfg.get("audio_endpoints_priority", "wav,pcm"))
            self.blocksize_spin.setValue(cfg.get("audio_blocksize", 1024))
            self.max_buffer_spin.setValue(cfg.get("audio_max_buffer_seconds", 2.0))
        except Exception as e:
            print(f"Error cargando valores de audio: {e}")

    def get_config(self):
        return {
            "audio_sample_rate": int(self.sample_rate_combo.currentText()),
            "audio_channels": 1 if self.channels_combo.currentIndex() == 0 else 2,
            "audio_volume": self.volume_spin.value(),
            "audio_detect_endpoint": self.detect_endpoint_cb.isChecked(),
            "audio_endpoints_priority": self.priority_edit.text(),
            "audio_blocksize": self.blocksize_spin.value(),
            "audio_max_buffer_seconds": self.max_buffer_spin.value(),
        }

    def apply_changes(self) -> bool:
        try:
            from core.settings_manager import settings_manager

            config = self.get_config()
            existing = settings_manager.get_advanced_settings()
            existing.update(config)
            settings_manager.save_advanced_settings(existing)

            from utils.config_loader import advanced_config
            advanced_config.reload()
            return True
        except Exception as e:
            print(f"Error aplicando config de audio: {e}")
            return False