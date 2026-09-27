"""
Tab de configuración del plugin motion_detector.

Incluye TODOS los parámetros de detección de movimiento,
tal como aparecen en la pestaña "Avanzado" del SettingsDialog.
"""
from PySide6.QtWidgets import (
    QVBoxLayout, QGridLayout, QGroupBox, QLabel,
    QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox,
    QScrollArea, QWidget
)
from PySide6.QtCore import Qt

from ui.settings_dialog_base import PluginConfigTab


class MotionDetectorConfigTab(PluginConfigTab):
    """
    Configuración completa del detector de movimiento.

    Cubre los 17 parámetros de motion del advanced_config.
    """

    # ==================== SCHEMA (para SettingsAPIImpl) ====================

    SCHEMA = {
        "motion_method": {"type": "str", "default": "adaptive"},
        "motion_use_shadow_removal": {"type": "bool", "default": True},
        "motion_use_shape_filter": {"type": "bool", "default": True},
        "motion_min_density": {"type": "float", "default": 0.3},
        "motion_min_consecutive_frames": {"type": "int", "default": 2},
        "motion_learning_rate": {"type": "float", "default": 0.001},
        "motion_reinit_interval": {"type": "float", "default": 10.0},
        "motion_history": {"type": "int", "default": 500},
        "motion_var_threshold": {"type": "int", "default": 16},
        "motion_blur_size": {"type": "int", "default": 5},
        "motion_max_width_resize": {"type": "int", "default": 640},
        "motion_iou_threshold": {"type": "float", "default": 0.3},
        "motion_max_aspect_ratio": {"type": "int", "default": 5},
        "motion_dilate_iterations": {"type": "int", "default": 2},
        "motion_max_area_ratio": {"type": "float", "default": 0.7},
        "motion_knn_dist2_threshold": {"type": "int", "default": 400},
    }

    def build_ui(self):
        # Registrar schema
        if self.context.settings is not None:
            self.context.settings.register_config_schema(
                self.plugin_name, self.SCHEMA
            )

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)

        # ============ Grupo 1: Básicos ============
        basic_group = QGroupBox("🎯 Básicos")
        basic_layout = QGridLayout(basic_group)
        basic_layout.setVerticalSpacing(10)
        basic_layout.setHorizontalSpacing(20)

        basic_layout.addWidget(QLabel("Método:"), 0, 0)
        self.method_combo = QComboBox()
        self.method_combo.addItems(["adaptive", "mog2", "frame_diff"])
        basic_layout.addWidget(self.method_combo, 0, 1)

        self.shadow_cb = QCheckBox("Eliminar sombras")
        basic_layout.addWidget(self.shadow_cb, 1, 0, 1, 2)

        self.shape_cb = QCheckBox("Filtrar por forma")
        basic_layout.addWidget(self.shape_cb, 2, 0, 1, 2)

        basic_layout.addWidget(QLabel("Densidad mínima:"), 3, 0)
        self.density_spin = QDoubleSpinBox()
        self.density_spin.setRange(0.0, 1.0)
        self.density_spin.setSingleStep(0.05)
        self.density_spin.setDecimals(2)
        basic_layout.addWidget(self.density_spin, 3, 1)

        basic_layout.addWidget(QLabel("Frames consecutivos:"), 4, 0)
        self.consecutive_spin = QSpinBox()
        self.consecutive_spin.setRange(1, 10)
        basic_layout.addWidget(self.consecutive_spin, 4, 1)

        basic_layout.addWidget(QLabel("Learning rate:"), 5, 0)
        self.learning_spin = QDoubleSpinBox()
        self.learning_spin.setRange(0.0001, 0.1)
        self.learning_spin.setSingleStep(0.001)
        self.learning_spin.setDecimals(4)
        basic_layout.addWidget(self.learning_spin, 5, 1)

        layout.addWidget(basic_group)

        # ============ Grupo 2: Fondo ============
        bg_group = QGroupBox("🔄 Fondo")
        bg_layout = QGridLayout(bg_group)
        bg_layout.setVerticalSpacing(10)
        bg_layout.setHorizontalSpacing(20)

        bg_layout.addWidget(QLabel("Reinit fondo (s):"), 0, 0)
        self.reinit_spin = QDoubleSpinBox()
        self.reinit_spin.setRange(1.0, 120.0)
        self.reinit_spin.setSingleStep(1.0)
        self.reinit_spin.setSuffix(" s")
        bg_layout.addWidget(self.reinit_spin, 0, 1)

        bg_layout.addWidget(QLabel("Historial:"), 1, 0)
        self.history_spin = QSpinBox()
        self.history_spin.setRange(50, 2000)
        self.history_spin.setSingleStep(50)
        bg_layout.addWidget(self.history_spin, 1, 1)

        bg_layout.addWidget(QLabel("Var threshold:"), 2, 0)
        self.var_spin = QSpinBox()
        self.var_spin.setRange(1, 100)
        bg_layout.addWidget(self.var_spin, 2, 1)

        bg_layout.addWidget(QLabel("KNN dist2 threshold:"), 3, 0)
        self.knn_spin = QSpinBox()
        self.knn_spin.setRange(50, 2000)
        self.knn_spin.setSingleStep(50)
        bg_layout.addWidget(self.knn_spin, 3, 1)

        layout.addWidget(bg_group)

        # ============ Grupo 3: Procesamiento ============
        proc_group = QGroupBox("🔧 Procesamiento")
        proc_layout = QGridLayout(proc_group)
        proc_layout.setVerticalSpacing(10)
        proc_layout.setHorizontalSpacing(20)

        proc_layout.addWidget(QLabel("Blur size:"), 0, 0)
        self.blur_spin = QSpinBox()
        self.blur_spin.setRange(3, 15)
        self.blur_spin.setSingleStep(2)
        proc_layout.addWidget(self.blur_spin, 0, 1)

        proc_layout.addWidget(QLabel("Max width resize:"), 1, 0)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(320, 1920)
        self.width_spin.setSingleStep(80)
        self.width_spin.setSuffix(" px")
        proc_layout.addWidget(self.width_spin, 1, 1)

        proc_layout.addWidget(QLabel("IoU threshold:"), 2, 0)
        self.iou_spin = QDoubleSpinBox()
        self.iou_spin.setRange(0.1, 0.9)
        self.iou_spin.setSingleStep(0.05)
        self.iou_spin.setDecimals(2)
        proc_layout.addWidget(self.iou_spin, 2, 1)

        proc_layout.addWidget(QLabel("Max aspect ratio:"), 3, 0)
        self.aspect_spin = QSpinBox()
        self.aspect_spin.setRange(2, 10)
        proc_layout.addWidget(self.aspect_spin, 3, 1)

        proc_layout.addWidget(QLabel("Dilate iterations:"), 4, 0)
        self.dilate_spin = QSpinBox()
        self.dilate_spin.setRange(1, 5)
        proc_layout.addWidget(self.dilate_spin, 4, 1)

        proc_layout.addWidget(QLabel("Max area ratio:"), 5, 0)
        self.area_spin = QDoubleSpinBox()
        self.area_spin.setRange(0.3, 0.95)
        self.area_spin.setSingleStep(0.05)
        self.area_spin.setDecimals(2)
        proc_layout.addWidget(self.area_spin, 5, 1)

        layout.addWidget(proc_group)

        layout.addStretch()
        scroll.setWidget(content)
        self.layout.addWidget(scroll)

        # Cargar valores
        self._load_values()

    # ==================== CARGA / GUARDADO ====================

    def _load_values(self):
        """Carga valores desde advanced_config."""
        try:
            from utils.config_loader import advanced_config
            cfg = advanced_config.get_all()

            self.method_combo.setCurrentText(cfg.get("motion_method", "adaptive"))
            self.shadow_cb.setChecked(cfg.get("motion_use_shadow_removal", True))
            self.shape_cb.setChecked(cfg.get("motion_use_shape_filter", True))
            self.density_spin.setValue(cfg.get("motion_min_density", 0.3))
            self.consecutive_spin.setValue(cfg.get("motion_min_consecutive_frames", 2))
            self.learning_spin.setValue(cfg.get("motion_learning_rate", 0.001))
            self.reinit_spin.setValue(cfg.get("motion_reinit_interval", 10.0))
            self.history_spin.setValue(cfg.get("motion_history", 500))
            self.var_spin.setValue(cfg.get("motion_var_threshold", 16))
            self.blur_spin.setValue(cfg.get("motion_blur_size", 5))
            self.width_spin.setValue(cfg.get("motion_max_width_resize", 640))
            self.iou_spin.setValue(cfg.get("motion_iou_threshold", 0.3))
            self.aspect_spin.setValue(cfg.get("motion_max_aspect_ratio", 5))
            self.dilate_spin.setValue(cfg.get("motion_dilate_iterations", 2))
            self.area_spin.setValue(cfg.get("motion_max_area_ratio", 0.7))
            self.knn_spin.setValue(cfg.get("motion_knn_dist2_threshold", 400))
        except Exception as e:
            print(f"Error cargando valores de motion_detector: {e}")

    def get_config(self):
        """Retorna los valores actuales (para guardar)."""
        return {
            "motion_method": self.method_combo.currentText(),
            "motion_use_shadow_removal": self.shadow_cb.isChecked(),
            "motion_use_shape_filter": self.shape_cb.isChecked(),
            "motion_min_density": self.density_spin.value(),
            "motion_min_consecutive_frames": self.consecutive_spin.value(),
            "motion_learning_rate": self.learning_spin.value(),
            "motion_reinit_interval": self.reinit_spin.value(),
            "motion_history": self.history_spin.value(),
            "motion_var_threshold": self.var_spin.value(),
            "motion_blur_size": self.blur_spin.value(),
            "motion_max_width_resize": self.width_spin.value(),
            "motion_iou_threshold": self.iou_spin.value(),
            "motion_max_aspect_ratio": self.aspect_spin.value(),
            "motion_dilate_iterations": self.dilate_spin.value(),
            "motion_max_area_ratio": self.area_spin.value(),
            "motion_knn_dist2_threshold": self.knn_spin.value(),
        }

    def apply_changes(self) -> bool:
        """
        Aplica los cambios al advanced_config y QSettings.

        Los motion_* keys van a advanced_settings (no a plugin_config),
        porque son parámetros globales del Core.
        """
        try:
            from core.settings_manager import settings_manager

            config = self.get_config()

            # ✅ Guardar en advanced_settings (los motion_* son del Core)
            existing = settings_manager.get_advanced_settings()
            existing.update(config)
            settings_manager.save_advanced_settings(existing)

            # ✅ Recargar advanced_config
            from utils.config_loader import advanced_config
            advanced_config.reload()

            return True
        except Exception as e:
            print(f"Error aplicando config de motion_detector: {e}")
            return False