"""
Editor de mejora de imagen interactivo - CON PRESETS Y CONTROLES AVANZADOS
"""
import cv2
import numpy as np
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                               QLabel, QPushButton, QSlider, QCheckBox,
                               QGroupBox, QGridLayout, QFrame, QSizePolicy,
                               QComboBox, QScrollArea, QApplication,
                               QProgressBar)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap, QImage, QKeyEvent

from utils.logger import get_logger
from utils.timer_manager import timer_manager
from .image_enhancer import ImageEnhancer

logger = get_logger("ImageEnhanceDialog")


class ImageEnhanceDialog(QDialog):
    """Editor interactivo de mejora de imagen con presets y controles avanzados."""

    _instance_counter = 0

    def __init__(self, original_frame: np.ndarray, parent=None):
        super().__init__(parent)
        self.original_frame = original_frame.copy()
        self.current_frame = original_frame.copy()
        self.user_accepted = False
        self._preset_override = None

        ImageEnhanceDialog._instance_counter += 1
        self._debounce_timer_name = f"enhance_dialog.debounce_{ImageEnhanceDialog._instance_counter}"
        self._preview_dirty = False

        self.setWindowTitle("🎨 Editor de Imagen - ProCamera")
        self.setMinimumSize(1250, 820)
        self.setModal(True)

        self._setup_ui()
        self._update_preview()
        logger.debug("ImageEnhanceDialog abierto")

    def _setup_ui(self):
        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0d1445, stop:1 #2a0a4a);
            }
            QLabel { color: white; }
            QGroupBox {
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 10px;
                margin-top: 10px;
                padding-top: 14px;
                font-weight: bold;
                color: #4da0c4;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 8px;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1a237e, stop:1 #4a148c);
                color: white;
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 50px;
                padding: 10px 24px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #283593, stop:1 #6a1b9a);
            }
            QPushButton[type="success"] {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2e7d32, stop:1 #43a047);
            }
            QPushButton[type="success"]:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #388e3c, stop:1 #4caf50);
            }
            QPushButton[type="secondary"] {
                background: rgba(255,255,255,0.08);
            }
            QPushButton[type="secondary"]:hover {
                background: rgba(255,255,255,0.16);
            }
            QPushButton[type="preset"] {
                background: rgba(77, 160, 196, 0.15);
                border: 1px solid rgba(77, 160, 196, 0.35);
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 11px;
                font-weight: 500;
                min-height: 30px;
            }
            QPushButton[type="preset"]:hover {
                background: rgba(77, 160, 196, 0.35);
                border-color: #4da0c4;
            }
            QPushButton[type="preset-active"] {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4da0c4, stop:1 #6a1b9a);
                border: 1px solid #4da0c4;
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 11px;
                font-weight: 700;
                min-height: 30px;
            }
            QSlider::groove:horizontal {
                background: rgba(255,255,255,0.1);
                height: 6px;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4da0c4, stop:1 #6a1b9a);
                width: 18px;
                height: 18px;
                border-radius: 9px;
                margin: -6px 0;
                border: 2px solid rgba(255,255,255,0.25);
            }
            QSlider::handle:horizontal:hover {
                border-color: #ffffff;
            }
            QCheckBox { color: rgba(255,255,255,0.85); spacing: 8px; font-size: 12px; }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                background: rgba(255,255,255,0.08);
                border: 2px solid rgba(255,255,255,0.2);
            }
            QCheckBox::indicator:checked {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4da0c4, stop:1 #6a1b9a);
                border-color: #4da0c4;
            }
            QComboBox {
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 6px;
                padding: 6px 10px;
                color: white;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background: #1a237e;
                color: white;
                selection-background-color: #4a148c;
            }
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                background: rgba(255,255,255,0.04);
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: rgba(77,160,196,0.5);
                border-radius: 5px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(77,160,196,0.8);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        # ==================== PANEL IZQUIERDO: CONTROLES ====================
        controls_scroll = QScrollArea()
        controls_scroll.setWidgetResizable(True)
        controls_scroll.setFixedWidth(420)

        controls = QFrame()
        controls.setStyleSheet("QFrame { background: transparent; }")
        c_layout = QVBoxLayout(controls)
        c_layout.setSpacing(12)

        # --- 1. Análisis de calidad ---
        quality_group = QGroupBox("📊 Análisis de Calidad")
        q_layout = QVBoxLayout(quality_group)
        q_layout.setSpacing(8)

        try:
            quality = ImageEnhancer.assess_quality(self.original_frame)

            score = quality["overall_score"]
            if score >= 0.8:
                color, txt = "#4CAF50", "Excelente"
            elif score >= 0.6:
                color, txt = "#8BC34A", "Buena"
            elif score >= 0.4:
                color, txt = "#FF9800", "Regular"
            else:
                color, txt = "#f44336", "Mala"

            score_label = QLabel(
                f"<b style='color:{color}; font-size:18px;'>"
                f"Calidad: {int(score*100)}% - {txt}</b>"
            )
            q_layout.addWidget(score_label)

            metrics = [
                ("Nitidez", quality["blur_score"]),
                ("Brillo", quality["brightness_score"]),
                ("Contraste", quality["contrast_score"]),
                ("Ruido", quality["noise_score"]),
                ("Exposición", quality["exposure_score"]),
                ("White Bal.", quality["white_balance_score"]),
                ("Saturación", quality["saturation_score"]),
            ]

            metrics_grid = QGridLayout()
            metrics_grid.setHorizontalSpacing(10)
            metrics_grid.setVerticalSpacing(4)

            for i, (name, val) in enumerate(metrics):
                row = i // 2
                col = (i % 2) * 3

                name_lbl = QLabel(f"{name}:")
                name_lbl.setStyleSheet("color: rgba(255,255,255,0.6); font-size: 11px;")
                metrics_grid.addWidget(name_lbl, row, col)

                bar_color = "#4CAF50" if val >= 0.7 else ("#FF9800" if val >= 0.4 else "#f44336")
                val_lbl = QLabel(
                    f"<span style='color:{bar_color}; font-weight:bold;'>"
                    f"{int(val*100)}%</span>"
                )
                val_lbl.setStyleSheet("font-size: 11px;")
                metrics_grid.addWidget(val_lbl, row, col + 1)

            q_layout.addLayout(metrics_grid)

            problems = quality.get("problems", [])
            if problems and problems[0] != "Buena calidad":
                for problem in problems[:3]:
                    lbl = QLabel(f"⚠️ {problem}")
                    lbl.setStyleSheet("color: #FF9800; font-size: 11px;")
                    lbl.setWordWrap(True)
                    q_layout.addWidget(lbl)

        except Exception as e:
            logger.debug(f"No se pudo evaluar calidad: {e}")
            q_layout.addWidget(QLabel("Análisis no disponible"))

        c_layout.addWidget(quality_group)

        # --- 2. PRESETS ---
        preset_group = QGroupBox("🎯 Presets Rápidos")
        p_layout = QGridLayout(preset_group)
        p_layout.setSpacing(6)

        self.preset_buttons = {}
        presets = [
            ("✨ Auto", "auto"),
            ("📄 Documento", "documento"),
            ("📷 Foto", "foto"),
            ("🌙 Noche", "noche"),
            ("👤 Retrato", "retrato"),
            ("🏞️ Paisaje", "paisaje"),
            ("🚫 Ninguno", "ninguno"),
        ]

        for i, (label, key) in enumerate(presets):
            btn = QPushButton(label)
            btn.setProperty("type", "preset")
            btn.clicked.connect(lambda checked=False, k=key: self._apply_preset(k))
            self.preset_buttons[key] = btn
            p_layout.addWidget(btn, i // 2, i % 2)

        c_layout.addWidget(preset_group)

        # --- 3. Ajustes manuales ---
        manual_group = QGroupBox("🎛️ Ajustes Manuales")
        m_layout = QGridLayout(manual_group)
        m_layout.setVerticalSpacing(10)
        m_layout.setHorizontalSpacing(10)

        m_layout.addWidget(QLabel("Brillo:"), 0, 0)
        self.brightness_slider = QSlider(Qt.Horizontal)
        self.brightness_slider.setRange(-100, 100)
        self.brightness_slider.setValue(0)
        self.brightness_slider.valueChanged.connect(self._on_manual_change)
        m_layout.addWidget(self.brightness_slider, 0, 1)
        self.brightness_val = QLabel("0")
        self.brightness_val.setMinimumWidth(45)
        self.brightness_val.setStyleSheet("color: #4da0c4; font-weight: bold;")
        m_layout.addWidget(self.brightness_val, 0, 2)
        self.brightness_slider.valueChanged.connect(
            lambda v: self.brightness_val.setText(str(v))
        )

        m_layout.addWidget(QLabel("Contraste:"), 1, 0)
        self.contrast_slider = QSlider(Qt.Horizontal)
        self.contrast_slider.setRange(50, 300)
        self.contrast_slider.setValue(100)
        self.contrast_slider.valueChanged.connect(self._on_manual_change)
        m_layout.addWidget(self.contrast_slider, 1, 1)
        self.contrast_val = QLabel("1.00")
        self.contrast_val.setMinimumWidth(45)
        self.contrast_val.setStyleSheet("color: #4da0c4; font-weight: bold;")
        m_layout.addWidget(self.contrast_val, 1, 2)
        self.contrast_slider.valueChanged.connect(
            lambda v: self.contrast_val.setText(f"{v/100:.2f}")
        )

        m_layout.addWidget(QLabel("Gamma:"), 2, 0)
        self.gamma_slider = QSlider(Qt.Horizontal)
        self.gamma_slider.setRange(50, 200)
        self.gamma_slider.setValue(100)
        self.gamma_slider.valueChanged.connect(self._on_manual_change)
        m_layout.addWidget(self.gamma_slider, 2, 1)
        self.gamma_val = QLabel("1.00")
        self.gamma_val.setMinimumWidth(45)
        self.gamma_val.setStyleSheet("color: #4da0c4; font-weight: bold;")
        m_layout.addWidget(self.gamma_val, 2, 2)
        self.gamma_slider.valueChanged.connect(
            lambda v: self.gamma_val.setText(f"{v/100:.2f}")
        )

        m_layout.addWidget(QLabel("Saturación:"), 3, 0)
        self.saturation_slider = QSlider(Qt.Horizontal)
        self.saturation_slider.setRange(0, 200)
        self.saturation_slider.setValue(100)
        self.saturation_slider.valueChanged.connect(self._on_manual_change)
        m_layout.addWidget(self.saturation_slider, 3, 1)
        self.saturation_val = QLabel("1.00")
        self.saturation_val.setMinimumWidth(45)
        self.saturation_val.setStyleSheet("color: #4da0c4; font-weight: bold;")
        m_layout.addWidget(self.saturation_val, 3, 2)
        self.saturation_slider.valueChanged.connect(
            lambda v: self.saturation_val.setText(f"{v/100:.2f}")
        )

        m_layout.addWidget(QLabel("Nitidez:"), 4, 0)
        self.sharpen_slider = QSlider(Qt.Horizontal)
        self.sharpen_slider.setRange(0, 30)
        self.sharpen_slider.setValue(10)
        self.sharpen_slider.valueChanged.connect(self._on_manual_change)
        m_layout.addWidget(self.sharpen_slider, 4, 1)
        self.sharpen_val = QLabel("1.0")
        self.sharpen_val.setMinimumWidth(45)
        self.sharpen_val.setStyleSheet("color: #4da0c4; font-weight: bold;")
        m_layout.addWidget(self.sharpen_val, 4, 2)
        self.sharpen_slider.valueChanged.connect(
            lambda v: self.sharpen_val.setText(f"{v/10:.1f}")
        )

        m_layout.addWidget(QLabel("Reducir ruido:"), 5, 0)
        self.denoise_slider = QSlider(Qt.Horizontal)
        self.denoise_slider.setRange(0, 30)
        self.denoise_slider.setValue(10)
        self.denoise_slider.valueChanged.connect(self._on_manual_change)
        m_layout.addWidget(self.denoise_slider, 5, 1)
        self.denoise_val = QLabel("10")
        self.denoise_val.setMinimumWidth(45)
        self.denoise_val.setStyleSheet("color: #4da0c4; font-weight: bold;")
        m_layout.addWidget(self.denoise_val, 5, 2)
        self.denoise_slider.valueChanged.connect(
            lambda v: self.denoise_val.setText(str(v))
        )

        c_layout.addWidget(manual_group)

        # --- 4. Opciones avanzadas ---
        options_group = QGroupBox("✅ Opciones de Procesamiento")
        o_layout = QVBoxLayout(options_group)
        o_layout.setSpacing(6)

        self.sharpen_check = QCheckBox("Aplicar nitidez (unsharp mask)")
        self.sharpen_check.stateChanged.connect(self._on_manual_change)
        o_layout.addWidget(self.sharpen_check)

        self.denoise_check = QCheckBox("Reducir ruido (NLM)")
        self.denoise_check.stateChanged.connect(self._on_manual_change)
        o_layout.addWidget(self.denoise_check)

        self.auto_contrast_check = QCheckBox("Auto-contraste (CLAHE)")
        self.auto_contrast_check.stateChanged.connect(self._on_manual_change)
        o_layout.addWidget(self.auto_contrast_check)

        self.exposure_check = QCheckBox("Corregir exposición")
        self.exposure_check.stateChanged.connect(self._on_manual_change)
        o_layout.addWidget(self.exposure_check)

        self.white_balance_check = QCheckBox("Balance de blancos (gray world)")
        self.white_balance_check.stateChanged.connect(self._on_manual_change)
        o_layout.addWidget(self.white_balance_check)

        self.vibrance_check = QCheckBox("Vibrance (colores vivos)")
        self.vibrance_check.stateChanged.connect(self._on_manual_change)
        o_layout.addWidget(self.vibrance_check)

        self.skin_smooth_check = QCheckBox("Suavizar piel (retratos)")
        self.skin_smooth_check.stateChanged.connect(self._on_manual_change)
        o_layout.addWidget(self.skin_smooth_check)

        self.binarize_check = QCheckBox("Binarizar (documentos B/N)")
        self.binarize_check.stateChanged.connect(self._on_manual_change)
        o_layout.addWidget(self.binarize_check)

        c_layout.addWidget(options_group)

        # --- 5. Viñeteo ---
        vignette_group = QGroupBox("🌑 Viñeteo")
        v_layout = QGridLayout(vignette_group)
        v_layout.addWidget(QLabel("Intensidad:"), 0, 0)
        self.vignette_slider = QSlider(Qt.Horizontal)
        self.vignette_slider.setRange(-50, 50)
        self.vignette_slider.setValue(0)
        self.vignette_slider.valueChanged.connect(self._on_manual_change)
        v_layout.addWidget(self.vignette_slider, 0, 1)
        self.vignette_val = QLabel("0.00")
        self.vignette_val.setMinimumWidth(45)
        self.vignette_val.setStyleSheet("color: #4da0c4; font-weight: bold;")
        v_layout.addWidget(self.vignette_val, 0, 2)
        self.vignette_slider.valueChanged.connect(
            lambda v: self.vignette_val.setText(f"{v/100:.2f}")
        )

        hint = QLabel("Negativo = oscurecer bordes | Positivo = aclarar centro")
        hint.setStyleSheet("color: rgba(255,255,255,0.4); font-size: 10px;")
        hint.setWordWrap(True)
        v_layout.addWidget(hint, 1, 0, 1, 3)

        c_layout.addWidget(vignette_group)

        # --- 6. Botones de acción ---
        reset_btn = QPushButton("🔄 Restaurar Original")
        reset_btn.setProperty("type", "secondary")
        reset_btn.clicked.connect(self._reset)
        c_layout.addWidget(reset_btn)

        c_layout.addStretch()

        btn_row = QHBoxLayout()

        discard_btn = QPushButton("❌ Descartar")
        discard_btn.setProperty("type", "secondary")
        discard_btn.clicked.connect(self.reject)
        btn_row.addWidget(discard_btn)

        save_btn = QPushButton("✅ Aplicar")
        save_btn.setProperty("type", "success")
        save_btn.clicked.connect(self._save_enhanced)
        btn_row.addWidget(save_btn)

        c_layout.addLayout(btn_row)

        controls_scroll.setWidget(controls)
        layout.addWidget(controls_scroll)

        # ==================== PANEL DERECHO: PREVIEW ====================
        preview = QFrame()
        p_layout = QVBoxLayout(preview)
        p_layout.setContentsMargins(0, 0, 0, 0)
        p_layout.setSpacing(8)

        view_row = QHBoxLayout()
        view_row.addWidget(QLabel("Vista:"))

        self.view_mode = QComboBox()
        self.view_mode.addItems(["Mejorada", "Original", "Comparación"])
        self.view_mode.currentTextChanged.connect(self._update_preview)
        self.view_mode.setFixedWidth(150)
        view_row.addWidget(self.view_mode)

        view_row.addStretch()

        self.info_label = QLabel("")
        self.info_label.setStyleSheet("color: rgba(255,255,255,0.6); font-size: 11px;")
        view_row.addWidget(self.info_label)

        p_layout.addLayout(view_row)

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview_label.setStyleSheet("""
            QLabel {
                background: rgba(0,0,0,0.3);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 10px;
                padding: 10px;
            }
        """)
        p_layout.addWidget(self.preview_label)

        status_row = QHBoxLayout()
        self.processing_label = QLabel("")
        self.processing_label.setStyleSheet("color: rgba(255,255,255,0.5); font-size: 11px;")
        status_row.addWidget(self.processing_label)

        status_row.addStretch()

        self.dimensions_label = QLabel("")
        self.dimensions_label.setStyleSheet("color: rgba(255,255,255,0.5); font-size: 11px;")
        status_row.addWidget(self.dimensions_label)

        p_layout.addLayout(status_row)

        layout.addWidget(preview, 1)

        self._update_dimensions_label()

    def _update_dimensions_label(self):
        h, w = self.current_frame.shape[:2]
        self.dimensions_label.setText(f"{w}x{h} px")

    # ==================== LÓGICA ====================

    def _apply_preset(self, preset_key: str):
        self._preset_override = preset_key

        for key, btn in self.preset_buttons.items():
            if key == preset_key:
                btn.setProperty("type", "preset-active")
            else:
                btn.setProperty("type", "preset")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        try:
            self.processing_label.setText(f"Aplicando preset: {preset_key}...")
            QApplication.processEvents()

            self.current_frame = ImageEnhancer.enhance(
                self.original_frame, preset=preset_key
            )

            self.processing_label.setText(f"✅ Preset '{preset_key}' aplicado")
            self._update_dimensions_label()
            self._show_current_frame()

            self._reset_manual_controls_silent()

        except Exception as e:
            logger.error(f"Error aplicando preset: {e}")
            self.processing_label.setText(f"❌ Error: {e}")

    def _reset_manual_controls_silent(self):
        for widget in [
            self.brightness_slider, self.contrast_slider, self.gamma_slider,
            self.saturation_slider, self.sharpen_slider, self.denoise_slider,
            self.vignette_slider
        ]:
            widget.blockSignals(True)

        for widget in [
            self.sharpen_check, self.denoise_check, self.auto_contrast_check,
            self.exposure_check, self.white_balance_check, self.vibrance_check,
            self.skin_smooth_check, self.binarize_check
        ]:
            widget.blockSignals(True)

        self.brightness_slider.setValue(0)
        self.contrast_slider.setValue(100)
        self.gamma_slider.setValue(100)
        self.saturation_slider.setValue(100)
        self.sharpen_slider.setValue(10)
        self.denoise_slider.setValue(10)
        self.vignette_slider.setValue(0)
        self.sharpen_check.setChecked(False)
        self.denoise_check.setChecked(False)
        self.auto_contrast_check.setChecked(False)
        self.exposure_check.setChecked(False)
        self.white_balance_check.setChecked(False)
        self.vibrance_check.setChecked(False)
        self.skin_smooth_check.setChecked(False)
        self.binarize_check.setChecked(False)

        for widget in [
            self.brightness_slider, self.contrast_slider, self.gamma_slider,
            self.saturation_slider, self.sharpen_slider, self.denoise_slider,
            self.vignette_slider
        ]:
            widget.blockSignals(False)

        for widget in [
            self.sharpen_check, self.denoise_check, self.auto_contrast_check,
            self.exposure_check, self.white_balance_check, self.vibrance_check,
            self.skin_smooth_check, self.binarize_check
        ]:
            widget.blockSignals(False)

    def _on_manual_change(self, *args):
        if self._preset_override is not None:
            self._preset_override = None
            for key, btn in self.preset_buttons.items():
                btn.setProperty("type", "preset")
                btn.style().unpolish(btn)
                btn.style().polish(btn)

        self._schedule_preview_update()

    def _schedule_preview_update(self):
        self._preview_dirty = True

        if timer_manager.exists(self._debounce_timer_name):
            timer_manager.stop(self._debounce_timer_name)

        timer_manager.create(
            self._debounce_timer_name,
            150,
            self._do_update_preview,
            single_shot=True,
            start=True
        )

    def _do_update_preview(self):
        if not self._preview_dirty:
            return
        self._preview_dirty = False
        self._update_preview()

    def _update_preview(self):
        try:
            if self._preset_override is not None:
                self._show_current_frame()
                return

            self.processing_label.setText("Procesando...")
            QApplication.processEvents()

            self.current_frame = ImageEnhancer.enhance(
                self.original_frame,
                denoise=self.denoise_check.isChecked(),
                sharpen=self.sharpen_check.isChecked(),
                brightness=self.brightness_slider.value(),
                contrast=self.contrast_slider.value() / 100.0,
                auto_contrast=self.auto_contrast_check.isChecked(),
                exposure_fix=self.exposure_check.isChecked(),
                sharpen_strength=self.sharpen_slider.value() / 10.0,
                denoise_strength=self.denoise_slider.value(),
                white_balance=self.white_balance_check.isChecked(),
                gamma=self.gamma_slider.value() / 100.0,
                saturation=self.saturation_slider.value() / 100.0,
                vibrance=self.vibrance_check.isChecked(),
                skin_smooth=self.skin_smooth_check.isChecked(),
                vignette=self.vignette_slider.value() / 100.0,
                binarize=self.binarize_check.isChecked(),
            )

            self.processing_label.setText("✅ Preview actualizado")
            self._update_dimensions_label()
            self._show_current_frame()

        except Exception as e:
            logger.error(f"Error preview: {e}", exc_info=True)
            self.processing_label.setText(f"❌ Error: {e}")

    def _show_current_frame(self):
        mode = self.view_mode.currentText()

        if mode == "Original":
            display = self.original_frame
            self.info_label.setText("Vista: Original")
        elif mode == "Mejorada":
            display = self.current_frame
            self.info_label.setText("Vista: Mejorada")
        else:
            h, w = self.original_frame.shape[:2]

            max_w = 1200
            if w * 2 + 10 > max_w:
                scale = max_w / (w * 2 + 10)
                new_w = int(w * scale)
                new_h = int(h * scale)
                left = cv2.resize(self.original_frame, (new_w, new_h))
                right = cv2.resize(self.current_frame, (new_w, new_h))
                comparison = np.zeros((new_h, new_w * 2 + 10, 3), dtype=np.uint8)
                comparison[:, :new_w] = left
                comparison[:, new_w + 10:] = right
            else:
                comparison = np.zeros((h, w * 2 + 10, 3), dtype=np.uint8)
                comparison[:, :w] = self.original_frame
                comparison[:, w + 10:] = self.current_frame

            display = comparison
            self.info_label.setText("Original (izq) | Mejorada (der)")

        try:
            rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            bytes_per_line = ch * w
            qt_image = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)

            lw = self.preview_label.width() - 20
            lh = self.preview_label.height() - 20

            if lw > 0 and lh > 0:
                pixmap = QPixmap.fromImage(qt_image)
                scaled = pixmap.scaled(
                    lw, lh,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self.preview_label.setPixmap(scaled)
        except Exception as e:
            logger.error(f"Error mostrando preview: {e}")

    def _reset(self):
        self._preset_override = None
        for key, btn in self.preset_buttons.items():
            btn.setProperty("type", "preset")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        self._reset_manual_controls_silent()

        self.current_frame = self.original_frame.copy()
        self.processing_label.setText("🔄 Restaurado al original")
        self._update_dimensions_label()
        self._show_current_frame()

    def _save_enhanced(self):
        self.user_accepted = True
        logger.info("Editor de imagen: cambios aplicados")
        self.accept()

    # ==================== EVENTOS ====================

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_S and event.modifiers() == Qt.ControlModifier:
            self._save_enhanced()
            return

        if event.key() == Qt.Key_Escape:
            self.reject()
            return

        if event.key() == Qt.Key_R and event.modifiers() == Qt.AltModifier:
            self._reset()
            return

        if event.key() == Qt.Key_E and event.modifiers() == Qt.AltModifier:
            self._apply_preset("auto")
            return

        if event.modifiers() == Qt.ControlModifier:
            preset_map = {
                Qt.Key_1: "auto",
                Qt.Key_2: "documento",
                Qt.Key_3: "foto",
                Qt.Key_4: "noche",
                Qt.Key_5: "retrato",
                Qt.Key_6: "paisaje",
                Qt.Key_7: "ninguno",
            }
            if event.key() in preset_map:
                self._apply_preset(preset_map[event.key()])
                return

        super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._show_current_frame()

    def closeEvent(self, event):
        try:
            timer_manager.stop(self._debounce_timer_name)
        except Exception:
            pass
        super().closeEvent(event)

    def get_result(self):
        return self.current_frame, self.user_accepted