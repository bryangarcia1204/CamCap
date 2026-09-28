"""
MotionCaptureDialog — Diálogo dedicado para gestionar el plugin
de captura de movimiento.

Soporta DOS modos:
  - Video File: procesa un archivo de video y exporta a JSON/CSV/BVH.
  - Live Camera: procesa frames en vivo desde las cámaras de CamCap
    y los envía a Blender por socket TCP en tiempo real.

Estructura:
  ┌──────────────────────────────────────────────────────────────┐
  │  🎬 Motion Capture Studio                                    │
  │  Modo: [📁 Video File] [📡 Live Camera]                      │
  ├──────────────────────────────┬───────────────────────────────┤
  │  INPUT (cambia según modo)    │  PREVIEW                      │
  │  CONFIG TRACKER (común)       │  - Frame actual               │
  │  OUTPUT (solo Video)          │  - Landmarks                  │
  ├──────────────────────────────┴───────────────────────────────┤
  │  [▶ Iniciar]  [⏹ Detener]   Status...                        │
  ├──────────────────────────────────────────────────────────────┤
  │  LOG                                                          │
  └──────────────────────────────────────────────────────────────┘
"""
import os
import time
from typing import Optional, Dict, Any

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QSpinBox,
    QDoubleSpinBox, QCheckBox, QFileDialog, QProgressBar,
    QGroupBox, QTextEdit, QMessageBox, QSplitter, QFrame,
    QSizePolicy, QApplication, QButtonGroup, QRadioButton,
    QStackedWidget, QWidget,
)
from PySide6.QtCore import Qt, QTimer, Signal, QThread, QObject
from PySide6.QtGui import QImage, QPixmap, QColor, QPainter, QPen

from utils.logger import get_logger
from utils.timer_manager import timer_manager

logger = get_logger("Plugin.MotionCaptureDialog")


# ============================================================
# HELPERS
# ============================================================

def format_time(seconds: float) -> str:
    """Formatea segundos como MM:SS."""
    if seconds < 0:
        return "--:--"
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def format_size(bytes_: int) -> str:
    """Formatea bytes como MB/KB."""
    if bytes_ < 1024:
        return f"{bytes_} B"
    elif bytes_ < 1024 * 1024:
        return f"{bytes_ / 1024:.1f} KB"
    else:
        return f"{bytes_ / 1024 / 1024:.1f} MB"


# ============================================================
# WORKER PARA MODO VIDEO (batch)
# ============================================================

class ProcessingWorker(QObject):
    """Worker que corre el VideoProcessor en un hilo separado."""

    progress = Signal(int, int, float, float)
    finished = Signal(str)
    log_message = Signal(str)

    def __init__(self, plugin, config: Dict[str, Any]):
        super().__init__()
        self._plugin = plugin
        self._config = config

    def run(self):
        try:
            def on_progress(p):
                self.progress.emit(
                    p.current_frame, p.total_frames,
                    p.fps_processing, p.eta_seconds,
                )

            def on_done(error):
                self.finished.emit(error or "")

            started = self._plugin.start_processing(
                self._config,
                on_progress=on_progress,
                on_done=on_done,
            )
            if not started:
                self.finished.emit("No se pudo iniciar el procesamiento")
        except Exception as e:
            logger.error(f"Error en worker: {e}", exc_info=True)
            self.finished.emit(str(e))


# ============================================================
# DIÁLOGO PRINCIPAL
# ============================================================

class MotionCaptureDialog(QDialog):
    """
    Diálogo dedicado para el plugin MotionCaptureExport.

    Modos:
      - Video File: procesa un archivo y exporta a JSON/CSV/BVH.
      - Live Camera: procesa frames en vivo y los envía por socket.
    """

    # Modos
    MODE_VIDEO = "video"
    MODE_LIVE = "live"

    def __init__(self, plugin, parent=None):
        super().__init__(parent)
        self._plugin = plugin
        self._mode = self.MODE_VIDEO

        # Estado modo video
        self._video_path = ""
        self._output_path = ""
        self._worker_thread: Optional[QThread] = None
        self._worker: Optional[ProcessingWorker] = None
        self._is_processing = False
        self._preview_enabled = True

        # Estado modo live
        self._live_capture = None
        self._socket_server = None
        self._is_live = False
        self._live_status_timer_name = "motion_capture_dialog.live_status"

        self.setWindowTitle("🎬 Motion Capture Studio")
        self.setMinimumSize(1150, 780)
        self.setModal(False)

        self._setup_ui()
        self._load_plugin_config()
        self._update_mode_ui()

        logger.debug("MotionCaptureDialog abierto")

    # ==================== UI ====================

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
                background: rgba(255,255,255,0.08);
                color: white;
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.15);
            }
            QPushButton:disabled {
                background: rgba(255,255,255,0.03);
                color: rgba(255,255,255,0.3);
            }
            QPushButton[type="primary"] {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2e7d32, stop:1 #43a047);
                border: none;
            }
            QPushButton[type="primary"]:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #388e3c, stop:1 #4caf50);
            }
            QPushButton[type="danger"] {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #c62828, stop:1 #e53935);
                border: none;
            }
            QPushButton[type="danger"]:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #d32f2f, stop:1 #ef5350);
            }
            QPushButton[type="live"] {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #6a1b9a, stop:1 #8e24aa);
                border: none;
            }
            QPushButton[type="live"]:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #7b1fa2, stop:1 #ab47bc);
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 6px;
                padding: 6px 10px;
                color: white;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #4da0c4;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background: #1a237e;
                color: white;
                selection-background-color: #4a148c;
            }
            QProgressBar {
                background: rgba(255,255,255,0.1);
                border: none;
                border-radius: 4px;
                height: 8px;
                text-align: center;
                color: white;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4da0c4, stop:1 #6a1b9a);
                border-radius: 4px;
            }
            QTextEdit {
                background: rgba(0,0,0,0.35);
                color: #ccc;
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 6px;
                font-family: Consolas, monospace;
                font-size: 11px;
            }
            QFrame#preview_frame {
                background: rgba(0,0,0,0.4);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 8px;
            }
            QFrame#mode_selector {
                background: rgba(255,255,255,0.03);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 8px;
                padding: 8px;
            }
            QRadioButton {
                color: white;
                font-weight: 600;
                padding: 6px 12px;
                spacing: 8px;
            }
            QRadioButton::indicator {
                width: 14px;
                height: 14px;
            }
            QRadioButton::indicator:checked {
                background: #4da0c4;
                border: 2px solid white;
                border-radius: 7px;
            }
            QRadioButton::indicator:unchecked {
                background: transparent;
                border: 2px solid rgba(255,255,255,0.3);
                border-radius: 7px;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # === Título ===
        title_row = QHBoxLayout()
        title = QLabel("🎬 Motion Capture Studio")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #4da0c4;")
        title_row.addWidget(title)
        title_row.addStretch()

        help_btn = QPushButton("❓ Ayuda")
        help_btn.setFixedHeight(30)
        help_btn.clicked.connect(self._show_help)
        title_row.addWidget(help_btn)

        main_layout.addLayout(title_row)

        # === Selector de modo ===
        mode_frame = QFrame()
        mode_frame.setObjectName("mode_selector")
        mode_layout = QHBoxLayout(mode_frame)
        mode_layout.setContentsMargins(8, 4, 8, 4)
        mode_layout.setSpacing(16)

        mode_label = QLabel("Modo:")
        mode_label.setStyleSheet(
            "color: rgba(255,255,255,0.7); font-weight: bold;"
        )
        mode_layout.addWidget(mode_label)

        self.mode_video_radio = QRadioButton("📁 Video File")
        self.mode_video_radio.setChecked(True)
        self.mode_video_radio.toggled.connect(self._on_mode_changed)
        mode_layout.addWidget(self.mode_video_radio)

        self.mode_live_radio = QRadioButton("📡 Live Camera")
        self.mode_live_radio.toggled.connect(self._on_mode_changed)
        mode_layout.addWidget(self.mode_live_radio)

        mode_layout.addStretch()

        # Info del modo
        self.mode_info_label = QLabel("")
        self.mode_info_label.setStyleSheet(
            "color: rgba(255,255,255,0.5); font-size: 11px;"
        )
        mode_layout.addWidget(self.mode_info_label)

        main_layout.addWidget(mode_frame)

        # === Splitter principal ===
        splitter = QSplitter(Qt.Horizontal)

        # ---------- Columna izquierda ----------
        left = QFrame()
        left.setMinimumWidth(400)
        left.setMaximumWidth(500)
        left_layout = QVBoxLayout(left)
        left_layout.setSpacing(12)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # --- INPUT (stacked widget, cambia según modo) ---
        self.input_stack = QStackedWidget()

        # Panel 1: Video File
        self.input_video_panel = self._create_video_input_panel()
        self.input_stack.addWidget(self.input_video_panel)

        # Panel 2: Live Camera
        self.input_live_panel = self._create_live_input_panel()
        self.input_stack.addWidget(self.input_live_panel)

        left_layout.addWidget(self.input_stack)

        # --- CONFIG TRACKER (común) ---
        tracker_group = QGroupBox("⚙️ Configuración del Tracker")
        tracker_layout = QGridLayout(tracker_group)
        tracker_layout.setVerticalSpacing(8)
        tracker_layout.setHorizontalSpacing(12)

        tracker_layout.addWidget(QLabel("Modelo YOLO:"), 0, 0)
        self.yolo_model_combo = QComboBox()
        self.yolo_model_combo.addItems([
            "yolov8n-pose.pt (más rápido)",
            "yolov8s-pose.pt (balance)",
            "yolov8m-pose.pt (más preciso)",
        ])
        tracker_layout.addWidget(self.yolo_model_combo, 0, 1)

        tracker_layout.addWidget(QLabel("Confianza YOLO:"), 1, 0)
        self.yolo_conf_spin = QDoubleSpinBox()
        self.yolo_conf_spin.setRange(0.1, 0.95)
        self.yolo_conf_spin.setSingleStep(0.05)
        self.yolo_conf_spin.setValue(0.4)
        self.yolo_conf_spin.setDecimals(2)
        tracker_layout.addWidget(self.yolo_conf_spin, 1, 1)

        tracker_layout.addWidget(QLabel("MediaPipe:"), 2, 0)
        self.mp_complexity_combo = QComboBox()
        self.mp_complexity_combo.addItems([
            "Lite (más rápido)",
            "Full (balance)",
            "Heavy (más preciso)",
        ])
        self.mp_complexity_combo.setCurrentIndex(1)
        tracker_layout.addWidget(self.mp_complexity_combo, 2, 1)

        # Frame skip solo aplica a modo Video
        self.frame_skip_label = QLabel("Frame skip:")
        tracker_layout.addWidget(self.frame_skip_label, 3, 0)
        self.frame_skip_spin = QSpinBox()
        self.frame_skip_spin.setRange(1, 10)
        self.frame_skip_spin.setValue(1)
        self.frame_skip_spin.setToolTip(
            "1 = procesar todos los frames\n"
            "2 = procesar 1 de cada 2\n"
            "Útil para videos largos"
        )
        tracker_layout.addWidget(self.frame_skip_spin, 3, 1)

        self.max_frames_label = QLabel("Máx. frames:")
        tracker_layout.addWidget(self.max_frames_label, 4, 0)
        self.max_frames_spin = QSpinBox()
        self.max_frames_spin.setRange(0, 100000)
        self.max_frames_spin.setValue(0)
        self.max_frames_spin.setSpecialValueText("Sin límite")
        tracker_layout.addWidget(self.max_frames_spin, 4, 1)

        left_layout.addWidget(tracker_group)

        # --- OUTPUT (solo modo Video) ---
        self.output_group = QGroupBox("💾 Exportación")
        output_layout = QGridLayout(self.output_group)
        output_layout.setVerticalSpacing(8)
        output_layout.setHorizontalSpacing(12)

        output_layout.addWidget(QLabel("Formato:"), 0, 0)
        self.format_combo = QComboBox()
        self.format_combo.addItems(["JSON", "CSV", "BVH"])
        self.format_combo.currentTextChanged.connect(self._on_format_changed)
        output_layout.addWidget(self.format_combo, 0, 1)

        output_layout.addWidget(QLabel("Archivo:"), 1, 0)
        out_row = QHBoxLayout()
        self.output_path_edit = QLineEdit()
        self.output_path_edit.setPlaceholderText("Se autogenera...")
        out_row.addWidget(self.output_path_edit, 1)

        out_browse_btn = QPushButton("📁")
        out_browse_btn.setFixedWidth(40)
        out_browse_btn.clicked.connect(self._browse_output)
        out_row.addWidget(out_browse_btn)

        output_layout.addLayout(out_row, 1, 1)

        self.open_output_check = QCheckBox("Abrir carpeta al terminar")
        self.open_output_check.setChecked(True)
        output_layout.addWidget(self.open_output_check, 2, 0, 1, 2)

        left_layout.addWidget(self.output_group)

        left_layout.addStretch()

        splitter.addWidget(left)

        # ---------- Columna derecha: preview ----------
        right = QFrame()
        right_layout = QVBoxLayout(right)
        right_layout.setSpacing(12)
        right_layout.setContentsMargins(0, 0, 0, 0)

        preview_group = QGroupBox("👁️ Vista Previa")
        preview_layout = QVBoxLayout(preview_group)

        self.preview_toggle = QCheckBox("Dibujar landmarks")
        self.preview_toggle.setChecked(True)
        self.preview_toggle.toggled.connect(self._on_preview_toggle)
        preview_layout.addWidget(self.preview_toggle)

        self.preview_frame = QFrame()
        self.preview_frame.setObjectName("preview_frame")
        self.preview_frame.setMinimumHeight(400)
        self.preview_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        pf_layout = QVBoxLayout(self.preview_frame)
        pf_layout.setContentsMargins(8, 8, 8, 8)

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview_label.setStyleSheet(
            "color: rgba(255,255,255,0.4); font-size: 13px; background: transparent;"
        )
        self.preview_label.setText("📼\nSelecciona un modo para empezar")
        pf_layout.addWidget(self.preview_label)

        preview_layout.addWidget(self.preview_frame, 1)

        self.preview_info = QLabel("")
        self.preview_info.setStyleSheet(
            "color: rgba(255,255,255,0.6); font-size: 11px;"
        )
        self.preview_info.setWordWrap(True)
        preview_layout.addWidget(self.preview_info)

        right_layout.addWidget(preview_group, 1)

        splitter.addWidget(right)

        splitter.setSizes([420, 730])
        main_layout.addWidget(splitter, 1)

        # === Barra de acciones ===
        actions = QHBoxLayout()

        self.start_btn = QPushButton("▶ Procesar")
        self.start_btn.setProperty("type", "primary")
        self.start_btn.setMinimumHeight(40)
        self.start_btn.setMinimumWidth(160)
        self.start_btn.clicked.connect(self._on_start_clicked)
        actions.addWidget(self.start_btn)

        self.stop_btn = QPushButton("⏹ Detener")
        self.stop_btn.setProperty("type", "danger")
        self.stop_btn.setMinimumHeight(40)
        self.stop_btn.setMinimumWidth(120)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop_clicked)
        actions.addWidget(self.stop_btn)

        actions.addStretch()

        self.open_folder_btn = QPushButton("📂 Abrir carpeta de salida")
        self.open_folder_btn.setEnabled(False)
        self.open_folder_btn.clicked.connect(self._open_output_folder)
        actions.addWidget(self.open_folder_btn)

        main_layout.addLayout(actions)

        # === Barra de estado ===
        status_row = QHBoxLayout()

        self.status_label = QLabel("Listo")
        self.status_label.setStyleSheet(
            "color: rgba(255,255,255,0.7); font-size: 12px;"
        )
        status_row.addWidget(self.status_label, 1)

        # Info de estado (solo live)
        self.live_status_label = QLabel("")
        self.live_status_label.setStyleSheet(
            "color: #4da0c4; font-size: 11px; font-weight: bold;"
        )
        status_row.addWidget(self.live_status_label)

        main_layout.addLayout(status_row)

        # === Progreso (solo video) ===
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setMinimumHeight(20)
        main_layout.addWidget(self.progress_bar)

        # === Log ===
        log_group = QGroupBox("📋 Log")
        log_layout = QVBoxLayout(log_group)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(130)
        self.log_text.setPlaceholderText("Los mensajes aparecerán aquí...")
        log_layout.addWidget(self.log_text)

        main_layout.addWidget(log_group)

    # ==================== PANELES DE INPUT ====================

    def _create_video_input_panel(self) -> QWidget:
        """Panel de input para modo Video File."""
        panel = QGroupBox("📁 Video de Entrada")
        layout = QVBoxLayout(panel)

        row1 = QHBoxLayout()
        self.video_path_edit = QLineEdit()
        self.video_path_edit.setPlaceholderText("Ruta del video...")
        self.video_path_edit.textChanged.connect(self._on_video_path_changed)
        row1.addWidget(self.video_path_edit, 1)

        browse_btn = QPushButton("📁")
        browse_btn.setFixedWidth(40)
        browse_btn.clicked.connect(self._browse_video)
        row1.addWidget(browse_btn)
        layout.addLayout(row1)

        self.video_info_label = QLabel("Sin video seleccionado")
        self.video_info_label.setStyleSheet(
            "color: rgba(255,255,255,0.5); font-size: 11px;"
        )
        self.video_info_label.setWordWrap(True)
        layout.addWidget(self.video_info_label)

        return panel

    def _create_live_input_panel(self) -> QWidget:
        """Panel de input para modo Live Camera."""
        panel = QGroupBox("📡 Live Camera → Blender")
        layout = QGridLayout(panel)
        layout.setVerticalSpacing(8)
        layout.setHorizontalSpacing(12)

        # Host
        layout.addWidget(QLabel("Host:"), 0, 0)
        self.live_host_edit = QLineEdit()
        self.live_host_edit.setText("127.0.0.1")
        self.live_host_edit.setToolTip(
            "Dirección donde escucha Blender.\n"
            "127.0.0.1 = misma máquina\n"
            "IP local = Blender en otra PC de la red"
        )
        layout.addWidget(self.live_host_edit, 0, 1)

        # Puerto
        layout.addWidget(QLabel("Puerto:"), 1, 0)
        self.live_port_spin = QSpinBox()
        self.live_port_spin.setRange(1024, 65535)
        self.live_port_spin.setValue(9999)
        layout.addWidget(self.live_port_spin, 1, 1)

        # FPS objetivo
        layout.addWidget(QLabel("FPS objetivo:"), 2, 0)
        self.live_fps_spin = QSpinBox()
        self.live_fps_spin.setRange(1, 60)
        self.live_fps_spin.setValue(15)
        self.live_fps_spin.setToolTip(
            "FPS de procesamiento y envío.\n"
            "En PC modestos: 10-15 fps.\n"
            "En PC potentes: 20-30 fps."
        )
        layout.addWidget(self.live_fps_spin, 2, 1)

        # Cámara (0 = todas, N = solo esa)
        layout.addWidget(QLabel("Cámara:"), 3, 0)
        self.live_camera_combo = QComboBox()
        self.live_camera_combo.addItem("Todas las cámaras", -1)
        layout.addWidget(self.live_camera_combo, 3, 1)

        # Botón para refrescar cámaras
        refresh_btn = QPushButton("🔄 Refrescar cámaras")
        refresh_btn.setFixedHeight(28)
        refresh_btn.clicked.connect(self._refresh_live_cameras)
        layout.addWidget(refresh_btn, 4, 0, 1, 2)

        # Info
        info = QLabel(
            "💡 Blender debe tener instalado el addon 'CamCap Bridge'\n"
            "   y estar escuchando en este host:puerto."
        )
        info.setStyleSheet(
            "color: rgba(255,255,255,0.5); font-size: 11px;"
        )
        info.setWordWrap(True)
        layout.addWidget(info, 5, 0, 1, 2)

        return panel

    # ==================== CAMBIO DE MODO ====================

    def _on_mode_changed(self):
        """Cuando cambia el modo Video/Live."""
        if self.mode_video_radio.isChecked():
            self._mode = self.MODE_VIDEO
        else:
            self._mode = self.MODE_LIVE

        self._update_mode_ui()

    def _update_mode_ui(self):
        """Actualiza la UI según el modo activo."""
        is_video = self._mode == self.MODE_VIDEO

        # Stack de input
        self.input_stack.setCurrentIndex(0 if is_video else 1)

        # Botón de salida solo en video
        self.output_group.setVisible(is_video)
        self.progress_bar.setVisible(is_video)
        self.open_folder_btn.setVisible(is_video)

        # Frame skip / max frames solo en video
        self.frame_skip_label.setVisible(is_video)
        self.frame_skip_spin.setVisible(is_video)
        self.max_frames_label.setVisible(is_video)
        self.max_frames_spin.setVisible(is_video)

        # Botón de start cambia según modo
        if is_video:
            self.start_btn.setText("▶ Procesar")
            self.start_btn.setProperty("type", "primary")
            self.mode_info_label.setText(
                "Procesa un archivo de video y exporta JSON/CSV/BVH"
            )
            self.preview_label.setText(
                "📼\nCarga un video para previsualizar"
            )
        else:
            self.start_btn.setText("📡 Iniciar Live")
            self.start_btn.setProperty("type", "live")
            self.mode_info_label.setText(
                "Procesa frames en vivo y los envía a Blender por socket"
            )
            self.preview_label.setText(
                "📡\nEsperando frames de las cámaras..."
            )
            self._refresh_live_cameras()

        # Forzar refresh de estilos
        self.start_btn.style().unpolish(self.start_btn)
        self.start_btn.style().polish(self.start_btn)

    def _refresh_live_cameras(self):
        """Rellena el combo de cámaras con las cámaras activas."""
        try:
            self.live_camera_combo.clear()
            self.live_camera_combo.addItem("Todas las cámaras", -1)

            from core.settings_manager import settings_manager
            cameras = settings_manager.get_cameras()
            for cam in cameras:
                self.live_camera_combo.addItem(
                    f"{cam.name} (ID {cam.id})", cam.id
                )
        except Exception as e:
            logger.debug(f"Error refrescando cámaras: {e}")

    # ==================== CONFIG ====================

    def _load_plugin_config(self):
        """Carga la config guardada del plugin."""
        try:
            if self._plugin.context.settings is not None:
                cfg = self._plugin.context.settings.get_plugin_config(self._plugin.NAME)
                if cfg:
                    self.yolo_model_combo.setCurrentIndex(
                        cfg.get("yolo_model_idx", 0)
                    )
                    self.yolo_conf_spin.setValue(cfg.get("yolo_conf", 0.4))
                    self.mp_complexity_combo.setCurrentIndex(
                        cfg.get("mp_complexity_idx", 1)
                    )
                    self.frame_skip_spin.setValue(cfg.get("frame_skip", 1))
                    self.max_frames_spin.setValue(cfg.get("max_frames", 0))
                    self.format_combo.setCurrentText(cfg.get("format", "JSON"))
                    # Live
                    self.live_host_edit.setText(cfg.get("live_host", "127.0.0.1"))
                    self.live_port_spin.setValue(cfg.get("live_port", 9999))
                    self.live_fps_spin.setValue(cfg.get("live_fps", 15))
                    # Modo
                    mode = cfg.get("mode", "video")
                    if mode == "live":
                        self.mode_live_radio.setChecked(True)
        except Exception as e:
            logger.debug(f"No se pudo cargar config: {e}")

    def _save_plugin_config(self):
        """Guarda la config actual."""
        try:
            if self._plugin.context.settings is not None:
                cfg = {
                    "yolo_model_idx": self.yolo_model_combo.currentIndex(),
                    "yolo_conf": self.yolo_conf_spin.value(),
                    "mp_complexity_idx": self.mp_complexity_combo.currentIndex(),
                    "frame_skip": self.frame_skip_spin.value(),
                    "max_frames": self.max_frames_spin.value(),
                    "format": self.format_combo.currentText(),
                    "live_host": self.live_host_edit.text().strip(),
                    "live_port": self.live_port_spin.value(),
                    "live_fps": self.live_fps_spin.value(),
                    "mode": self._mode,
                }
                self._plugin.context.settings.set_plugin_config(
                    self._plugin.NAME, cfg
                )
        except Exception as e:
            logger.debug(f"No se pudo guardar config: {e}")

    # ==================== SELECTORES ====================

    def _browse_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar video",
            "",
            "Videos (*.mp4 *.mkv *.avi *.mov *.webm *.flv *.wmv);;Todos (*)",
        )
        if path:
            self.video_path_edit.setText(path)

    def _on_video_path_changed(self, path: str):
        self._video_path = path.strip()

        if not self._video_path or not os.path.isfile(self._video_path):
            self.video_info_label.setText("Sin video seleccionado")
            self.preview_label.setText("📼\nCarga un video para previsualizar")
            return

        try:
            import cv2
            cap = cv2.VideoCapture(self._video_path)
            if cap.isOpened():
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = cap.get(cv2.CAP_PROP_FPS)
                frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                duration = frames / fps if fps > 0 else 0
                size = os.path.getsize(self._video_path)

                info = (
                    f"📐 {w}x{h}  •  🎞️ {fps:.1f} fps  •  "
                    f"📊 {frames} frames  •  ⏱️ {format_time(duration)}  •  "
                    f"💾 {format_size(size)}"
                )
                self.video_info_label.setText(info)

                ret, frame = cap.read()
                if ret:
                    self._show_preview_frame(frame, [])
                cap.release()
            else:
                self.video_info_label.setText("⚠️ No se pudo abrir el video")
        except Exception as e:
            self.video_info_label.setText(f"⚠️ Error: {e}")

        base = os.path.splitext(self._video_path)[0]
        fmt = self.format_combo.currentText().lower()
        default_output = f"{base}_mocap.{fmt}"
        self.output_path_edit.setText(default_output)
        self._output_path = default_output

    def _on_format_changed(self, fmt: str):
        if not self.output_path_edit.text().strip():
            return
        current = self.output_path_edit.text().strip()
        base = os.path.splitext(current)[0]
        self.output_path_edit.setText(f"{base}.{fmt.lower()}")

    def _browse_output(self):
        fmt = self.format_combo.currentText().lower()
        filter_str = f"{self.format_combo.currentText()} (*.{fmt})"
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar como",
            self.output_path_edit.text() or "",
            filter_str,
        )
        if path:
            if not path.endswith(f".{fmt}"):
                path = f"{path}.{fmt}"
            self.output_path_edit.setText(path)

    def _on_preview_toggle(self, enabled: bool):
        self._preview_enabled = enabled

    # ==================== PREVIEW ====================

    def _show_preview_frame(self, frame_bgr, persons):
        """Muestra un frame con landmarks dibujados."""
        try:
            import cv2
            import numpy as np

            vis = frame_bgr.copy()

            if self._preview_enabled and persons:
                for person in persons:
                    x, y, w, h = person.bbox
                    cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 255, 0), 2)

                    label = f"ID {person.track_id}  {person.confidence:.2f}"
                    cv2.putText(
                        vis, label, (x, max(20, y - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1,
                    )

                    if person.landmarks:
                        self._draw_landmarks(vis, person.landmarks, x, y, w, h)

            rgb = cv2.cvtColor(vis, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            bytes_per_line = ch * w
            qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)

            pixmap = QPixmap.fromImage(qimg)
            label_size = self.preview_label.size()
            if label_size.width() > 10 and label_size.height() > 10:
                scaled = pixmap.scaled(
                    label_size.width() - 4,
                    label_size.height() - 4,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
                self.preview_label.setPixmap(scaled)
            else:
                self.preview_label.setPixmap(pixmap)

            self.preview_info.setText(
                f"Frame {w}x{h}  •  "
                f"{len(persons) if persons else 0} persona(s) detectada(s)"
            )
        except Exception as e:
            logger.debug(f"Error mostrando preview: {e}")

    def _draw_landmarks(self, vis, landmarks, bbox_x, bbox_y, bbox_w, bbox_h):
        """Dibuja los 33 landmarks de MediaPipe."""
        try:
            import cv2

            CONNECTIONS = [
                (0, 1), (1, 2), (2, 3), (3, 7),
                (0, 4), (4, 5), (5, 6), (6, 8),
                (9, 10),
                (11, 12), (11, 13), (13, 15), (15, 17), (15, 19), (15, 21),
                (12, 14), (14, 16), (16, 18), (16, 20), (16, 22),
                (11, 23), (12, 24), (23, 24),
                (23, 25), (25, 27), (27, 29), (29, 31),
                (24, 26), (26, 28), (28, 30), (30, 32),
            ]

            points = []
            for lm in landmarks:
                nx, ny, _, vis_ = lm
                px = int(bbox_x + nx * bbox_w)
                py = int(bbox_y + ny * bbox_h)
                points.append((px, py, vis_))

            for a, b in CONNECTIONS:
                if a < len(points) and b < len(points):
                    pa = points[a]
                    pb = points[b]
                    if pa[2] > 0.3 and pb[2] > 0.3:
                        cv2.line(vis, (pa[0], pa[1]), (pb[0], pb[1]),
                                 (0, 255, 255), 2)

            for px, py, vis_ in points:
                if vis_ > 0.3:
                    cv2.circle(vis, (px, py), 3, (255, 0, 255), -1)
        except Exception as e:
            logger.debug(f"Error dibujando landmarks: {e}")

    # ==================== ACCIÓN PRINCIPAL ====================

    def _on_start_clicked(self):
        """Arranca según el modo activo."""
        if self._mode == self.MODE_VIDEO:
            self._on_process_video_clicked()
        else:
            self._on_start_live_clicked()

    def _on_stop_clicked(self):
        """Detiene según el modo activo."""
        if self._mode == self.MODE_VIDEO:
            self._on_stop_video_clicked()
        else:
            self._on_stop_live_clicked()

    # ==================== MODO VIDEO ====================

    def _on_process_video_clicked(self):
        """Valida y arranca el procesamiento de video."""
        video_path = self.video_path_edit.text().strip()
        output_path = self.output_path_edit.text().strip()

        if not video_path:
            QMessageBox.warning(self, "Error", "Selecciona un video primero")
            return
        if not os.path.isfile(video_path):
            QMessageBox.warning(self, "Error", f"El video no existe:\n{video_path}")
            return
        if not output_path:
            QMessageBox.warning(self, "Error", "Selecciona una ruta de salida")
            return

        if self._plugin._tracker is None:
            QMessageBox.warning(
                self, "Error",
                "El tracker no está cargado.\n\n"
                "Instala las dependencias:\n"
                "  pip install ultralytics mediapipe opencv-python\n\n"
                "Luego reinicia la aplicación."
            )
            return

        config = {
            "video_path": video_path,
            "output_path": output_path,
            "output_format": self.format_combo.currentText().lower(),
            "yolo_model": self.yolo_model_combo.currentText().split(" ")[0],
            "yolo_conf": self.yolo_conf_spin.value(),
            "mp_complexity": self.mp_complexity_combo.currentIndex(),
            "frame_skip": self.frame_skip_spin.value(),
            "max_frames": self.max_frames_spin.value(),
        }

        self._save_plugin_config()

        self._is_processing = True
        self._output_path = output_path
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.open_folder_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_label.setText("Iniciando procesamiento...")
        self._log(f"▶ Procesando: {os.path.basename(video_path)}")
        self._log(f"   YOLO: {config['yolo_model']} (conf={config['yolo_conf']})")
        self._log(f"   MediaPipe complexity: {config['mp_complexity']}")
        self._log(f"   Frame skip: {config['frame_skip']}")
        self._log(f"   Salida: {output_path}")

        self._worker = ProcessingWorker(self._plugin, config)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_processing_finished)

        self._worker_thread = QThread()
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)
        self._worker_thread.start()

    def _on_stop_video_clicked(self):
        """Solicita detener el procesamiento de video."""
        if not self._is_processing:
            return
        self._log("⏹ Detención solicitada...")
        self.status_label.setText("Deteniendo...")
        self._plugin.stop_processing()

    def _on_progress(self, current: int, total: int, fps: float, eta: float):
        if total <= 0:
            return
        percent = int((current / total) * 100)
        self.progress_bar.setValue(percent)
        self.status_label.setText(
            f"Frame {current}/{total}  •  {fps:.1f} fps  •  "
            f"ETA {format_time(eta)}"
        )

    def _on_processing_finished(self, error: str):
        """Cuando termina el procesamiento de video."""
        self._is_processing = False
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

        if self._worker_thread is not None:
            self._worker_thread.quit()
            self._worker_thread.wait(2000)
            self._worker_thread = None
        self._worker = None

        if error:
            self._log(f"❌ Error: {error}")
            self.status_label.setText(f"❌ Error")
            QMessageBox.critical(self, "Error", error)
        else:
            self.progress_bar.setValue(100)
            self.status_label.setText("✅ Completado")
            self._log(f"✅ Procesamiento completado")
            self._log(f"   Archivo: {self._output_path}")
            self.open_folder_btn.setEnabled(True)

            if self.open_output_check.isChecked():
                self._open_output_folder()

            QMessageBox.information(
                self, "Éxito",
                f"Captura exportada a:\n{self._output_path}"
            )

    # ==================== MODO LIVE ====================

    def _on_start_live_clicked(self):
        """Arranca el modo Live usando el plugin."""
        if self._plugin._tracker is None:
            QMessageBox.warning(
                self, "Error",
                "El tracker no está cargado.\n\n"
                "Instala las dependencias:\n"
                "  pip install ultralytics mediapipe opencv-python\n\n"
                "Luego reinicia la aplicación."
            )
            return

        host = self.live_host_edit.text().strip() or "127.0.0.1"
        port = self.live_port_spin.value()
        target_fps = self.live_fps_spin.value()
        camera_id = self.live_camera_combo.currentData()
        if camera_id is not None and camera_id < 0:
            camera_id = None

        self._save_plugin_config()

        # Arrancar usando el plugin
        ok = self._plugin.start_live(
            host=host,
            port=port,
            target_fps=target_fps,
            camera_id=camera_id,
            on_client_connected=self._on_client_connected,
            on_client_disconnected=self._on_client_disconnected,
        )

        if not ok:
            QMessageBox.critical(
                self, "Error",
                f"No se pudo arrancar el Live en {host}:{port}\n\n"
                f"Verifica que el puerto esté libre."
            )
            return

        # Actualizar UI
        self._is_live = True
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status_label.setText(
            f"📡 Live activo en {host}:{port} — esperando cliente..."
        )
        self._log(f"📡 Live iniciado")
        self._log(f"   Servidor: {host}:{port}")
        self._log(f"   FPS objetivo: {target_fps}")
        if camera_id is not None:
            self._log(f"   Cámara: {self.live_camera_combo.currentText()}")
        else:
            self._log(f"   Cámara: Todas")

        # Timer para actualizar stats
        timer_manager.create(
            self._live_status_timer_name,
            1000,
            self._update_live_status,
            start=True,
        )

    def _on_stop_live_clicked(self):
        """Detiene el modo Live usando el plugin."""
        if not self._is_live:
            return

        self._log("⏹ Deteniendo Live...")
        self.status_label.setText("Deteniendo...")

        try:
            self._plugin.stop_live()
        except Exception as e:
            logger.debug(f"Error deteniendo live: {e}")

        try:
            timer_manager.stop(self._live_status_timer_name)
        except Exception:
            pass

        self._is_live = False
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText("Listo")
        self.live_status_label.setText("")
        self._log("✅ Live detenido")

    def _update_live_status(self):
        """Actualiza el label de stats en vivo usando el plugin."""
        if not self._is_live:
            return

        try:
            stats = self._plugin.get_live_stats()
        except Exception:
            return

        parts = []

        if stats.get("client_connected"):
            addr = stats.get("client_address")
            if addr:
                parts.append(f"🔗 {addr[0]}:{addr[1]}")
            else:
                parts.append("🔗 Cliente conectado")
        else:
            parts.append("⏸ Sin cliente")

        fps = stats.get("effective_fps", 0.0)
        frames = stats.get("frames_processed", 0)
        sent = stats.get("frames_sent", 0)
        skipped = stats.get("frames_skipped", 0)

        parts.append(f"⚡ {fps:.1f} fps")
        parts.append(f"📤 {sent} enviados")
        if skipped > 0:
            parts.append(f"⏭ {skipped} saltados")

        self.live_status_label.setText("  •  ".join(parts))

    def _on_client_connected(self, address):
        """Callback cuando Blender se conecta."""
        try:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self._log(
                f"🔗 Cliente conectado desde {address}"
            ))
            QTimer.singleShot(0, lambda: self.status_label.setText(
                f"🔗 Cliente conectado desde {address}"
            ))
        except Exception as e:
            logger.debug(f"Error en callback connect: {e}")

    def _on_client_disconnected(self, address):
        """Callback cuando Blender se desconecta."""
        try:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self._log(
                f"🔌 Cliente desconectado: {address}"
            ))
            QTimer.singleShot(0, lambda: self.status_label.setText(
                "📡 Esperando cliente..."
            ))
        except Exception as e:
            logger.debug(f"Error en callback disconnect: {e}")

    # ==================== ACCIONES COMUNES ====================

    def _open_output_folder(self):
        """Abre la carpeta del archivo de salida."""
        if not self._output_path:
            return
        folder = os.path.dirname(self._output_path)
        if not os.path.isdir(folder):
            return
        try:
            import subprocess
            import platform
            system = platform.system()
            if system == "Windows":
                os.startfile(folder)
            elif system == "Darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception as e:
            logger.debug(f"Error abriendo carpeta: {e}")

    def _log(self, msg: str):
        """Añade un mensaje al log."""
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {msg}")
        logger.debug(msg)

    def _show_help(self):
        QMessageBox.information(
            self, "🎬 Motion Capture Studio — Ayuda",
            "El Studio tiene DOS modos:\n\n"
            "📁 Video File:\n"
            "   Procesa un archivo de video y exporta JSON/CSV/BVH.\n"
            "   Útil para analizar grabaciones pasadas.\n\n"
            "📡 Live Camera:\n"
            "   Procesa frames en vivo desde las cámaras de CamCap\n"
            "   y los envía a Blender por socket en tiempo real.\n"
            "   Requiere el addon 'CamCap Bridge' en Blender.\n\n"
            "Flujo del pipeline:\n"
            "   Frame → YOLO detecta personas → MediaPipe extrae 33\n"
            "   landmarks → exportar o enviar por socket.\n\n"
            "Recomendaciones:\n"
            "   • PC de bajos recursos: 'yolov8n-pose.pt' + 'Lite' + fps 10.\n"
            "   • PC potente: 'yolov8s-pose.pt' + 'Full' + fps 20-30.\n\n"
            "El addon de Blender 'CamCap Bridge' está en:\n"
            "   plugins/motion_capture_export/blender_addon/"
        )

    # ==================== CIERRE ====================

    def closeEvent(self, event):
        """Al cerrar, detener todo."""
        # Detener live si está activo
        if self._is_live:
            reply = QMessageBox.question(
                self, "Confirmar",
                "El modo Live está activo.\n¿Detenerlo y cerrar?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                event.ignore()
                return
            self._on_stop_live_clicked()

        # Detener procesamiento de video
        if self._is_processing:
            reply = QMessageBox.question(
                self, "Confirmar",
                "Hay un procesamiento en curso.\n¿Detenerlo y cerrar?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                event.ignore()
                return

            self._plugin.stop_processing()
            if self._worker_thread is not None:
                self._worker_thread.quit()
                self._worker_thread.wait(2000)

        self._save_plugin_config()
        super().closeEvent(event)