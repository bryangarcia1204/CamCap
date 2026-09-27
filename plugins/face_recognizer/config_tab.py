"""
Tab de configuración del plugin face_recognizer.

Incluye:
- ✅ Checkbox de ACTIVACIÓN (face_enabled)
- Todos los parámetros del reconocimiento facial
"""
from PySide6.QtWidgets import (
    QVBoxLayout, QGridLayout, QGroupBox, QLabel,
    QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox,
    QScrollArea, QWidget
)

from ui.settings_dialog_base import PluginConfigTab


class FaceRecognizerConfigTab(PluginConfigTab):
    """Configuración completa del reconocimiento facial."""

    SCHEMA = {
        "face_enabled": {"type": "bool", "default": False},   # ← NUEVO
        "face_detector_model": {"type": "str", "default": "sface"},
        "face_auto_register_unknown": {"type": "bool", "default": True},
        "face_min_face_size": {"type": "int", "default": 20},
        "face_recognition_scale": {"type": "float", "default": 0.25},
        "face_detector_score_threshold": {"type": "float", "default": 0.9},
        "face_nms_threshold": {"type": "float", "default": 0.3},
        "face_top_k": {"type": "int", "default": 5000},
        "face_sface_threshold": {"type": "float", "default": 0.363},
        "face_input_size": {"type": "int", "default": 320},
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

        # ============ GRUPO 0: ACTIVACIÓN ============
        activation_group = QGroupBox("🎯 Activación")
        activation_layout = QVBoxLayout(activation_group)

        self.enabled_cb = QCheckBox("👤 Activar reconocimiento facial")
        self.enabled_cb.setToolTip(
            "Cuando está activo, se detectan y reconocen caras en los frames. "
            "Consume más CPU que el detector de movimiento."
        )
        activation_layout.addWidget(self.enabled_cb)

        note = QLabel(
            "💡 Requiere modelos ONNX en plugins/face_recognizer/models/:\n"
            "   • face_detection_yunet_2023mar.onnx\n"
            "   • face_recognition_sface_2021dec.onnx"
        )
        note.setStyleSheet("color: rgba(255,255,255,0.6); font-size: 11px;")
        note.setWordWrap(True)
        activation_layout.addWidget(note)

        layout.addWidget(activation_group)

        # ============ Grupo 1: Modelo y detección ============
        model_group = QGroupBox("🧠 Modelo y Detección")
        model_layout = QGridLayout(model_group)
        model_layout.setVerticalSpacing(10)
        model_layout.setHorizontalSpacing(20)

        model_layout.addWidget(QLabel("Modelo:"), 0, 0)
        self.model_combo = QComboBox()
        self.model_combo.addItems(["sface", "dlib", "mediapipe"])
        model_layout.addWidget(self.model_combo, 0, 1)

        model_layout.addWidget(QLabel("Score threshold:"), 1, 0)
        self.score_spin = QDoubleSpinBox()
        self.score_spin.setRange(0.1, 1.0)
        self.score_spin.setSingleStep(0.05)
        self.score_spin.setDecimals(2)
        model_layout.addWidget(self.score_spin, 1, 1)

        model_layout.addWidget(QLabel("NMS threshold:"), 2, 0)
        self.nms_spin = QDoubleSpinBox()
        self.nms_spin.setRange(0.1, 0.9)
        self.nms_spin.setSingleStep(0.05)
        self.nms_spin.setDecimals(2)
        model_layout.addWidget(self.nms_spin, 2, 1)

        model_layout.addWidget(QLabel("Top K:"), 3, 0)
        self.topk_spin = QSpinBox()
        self.topk_spin.setRange(100, 10000)
        self.topk_spin.setSingleStep(100)
        model_layout.addWidget(self.topk_spin, 3, 1)

        model_layout.addWidget(QLabel("Input size detector:"), 4, 0)
        self.input_spin = QSpinBox()
        self.input_spin.setRange(160, 640)
        self.input_spin.setSingleStep(32)
        self.input_spin.setSuffix(" px")
        model_layout.addWidget(self.input_spin, 4, 1)

        layout.addWidget(model_group)

        # ============ Grupo 2: Reconocimiento ============
        recog_group = QGroupBox("👤 Reconocimiento")
        recog_layout = QGridLayout(recog_group)
        recog_layout.setVerticalSpacing(10)
        recog_layout.setHorizontalSpacing(20)

        recog_layout.addWidget(QLabel("Tamaño mín. rostro:"), 0, 0)
        self.min_size_spin = QSpinBox()
        self.min_size_spin.setRange(10, 200)
        self.min_size_spin.setSuffix(" px")
        recog_layout.addWidget(self.min_size_spin, 0, 1)

        recog_layout.addWidget(QLabel("Escala detección:"), 1, 0)
        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(0.1, 1.0)
        self.scale_spin.setSingleStep(0.05)
        self.scale_spin.setDecimals(2)
        recog_layout.addWidget(self.scale_spin, 1, 1)

        recog_layout.addWidget(QLabel("SFace threshold:"), 2, 0)
        self.sface_spin = QDoubleSpinBox()
        self.sface_spin.setRange(0.1, 0.9)
        self.sface_spin.setSingleStep(0.01)
        self.sface_spin.setDecimals(3)
        recog_layout.addWidget(self.sface_spin, 2, 1)

        self.auto_register_cb = QCheckBox("Auto-registrar desconocidos")
        recog_layout.addWidget(self.auto_register_cb, 3, 0, 1, 2)

        layout.addWidget(recog_group)

        # Info
        info_group = QGroupBox("ℹ️ Info")
        info_layout = QVBoxLayout(info_group)
        info_label = QLabel(
            "💡 Fotos de personas conocidas en:\n"
            "   known_faces/  (una o más fotos por persona)\n\n"
            "   Ejemplo: Brayan.jpg, Brayan_1.jpg, Brayan_2.jpg\n"
            "   → Todos se agrupan como 'Brayan'"
        )
        info_label.setStyleSheet("color: rgba(255,255,255,0.6); font-size: 11px;")
        info_label.setWordWrap(True)
        info_layout.addWidget(info_label)
        layout.addWidget(info_group)

        layout.addStretch()
        scroll.setWidget(content)
        self.layout.addWidget(scroll)

        self._load_values()

    def _load_values(self):
        try:
            # 1. Activación
            from core.settings_manager import settings_manager
            det = settings_manager.get_detection_settings()
            self.enabled_cb.setChecked(det.get("face_enabled", False))

            # 2. Ajustes avanzados
            from utils.config_loader import advanced_config
            cfg = advanced_config.get_all()

            self.model_combo.setCurrentText(cfg.get("face_detector_model", "sface"))
            self.auto_register_cb.setChecked(cfg.get("face_auto_register_unknown", True))
            self.min_size_spin.setValue(cfg.get("face_min_face_size", 20))
            self.scale_spin.setValue(cfg.get("face_recognition_scale", 0.25))
            self.score_spin.setValue(cfg.get("face_detector_score_threshold", 0.9))
            self.nms_spin.setValue(cfg.get("face_nms_threshold", 0.3))
            self.topk_spin.setValue(cfg.get("face_top_k", 5000))
            self.sface_spin.setValue(cfg.get("face_sface_threshold", 0.363))
            self.input_spin.setValue(cfg.get("face_input_size", 320))
        except Exception as e:
            print(f"Error cargando valores de face_recognizer: {e}")

    def get_config(self):
        return {
            "face_detector_model": self.model_combo.currentText(),
            "face_auto_register_unknown": self.auto_register_cb.isChecked(),
            "face_min_face_size": self.min_size_spin.value(),
            "face_recognition_scale": self.scale_spin.value(),
            "face_detector_score_threshold": self.score_spin.value(),
            "face_nms_threshold": self.nms_spin.value(),
            "face_top_k": self.topk_spin.value(),
            "face_sface_threshold": self.sface_spin.value(),
            "face_input_size": self.input_spin.value(),
        }

    def apply_changes(self) -> bool:
        try:
            from core.settings_manager import settings_manager
            from utils.config_loader import advanced_config

            enabled = self.enabled_cb.isChecked()

            # 1. Activación
            det = settings_manager.get_detection_settings()
            det["face_enabled"] = enabled
            settings_manager.save_detection_settings(det)

            # 2. Ajustes
            config = self.get_config()
            existing = settings_manager.get_advanced_settings()
            existing.update(config)
            existing["face_enabled"] = enabled
            settings_manager.save_advanced_settings(existing)

            advanced_config.reload()
            return True
        except Exception as e:
            print(f"Error aplicando config de face_recognizer: {e}")
            return False