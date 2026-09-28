"""
MotionCaptureDialog — Diálogo dedicado para gestionar el plugin
de captura de movimiento.

Estructura:
  ┌──────────────────────────────────────────────────────────────┐
  │  🎬 Motion Capture Studio                                    │
  ├──────────────────────────────┬───────────────────────────────┤
  │  INPUT                        │  PREVIEW                      │
  │  - Selector de video          │  - Frame actual               │
  │  - Info del video             │  - Landmarks dibujados        │
  │  - Botón procesar             │  - Bounding boxes             │
  │                               │  - Track IDs                  │
  │  CONFIG TRACKER               │                               │
  │  - Modelo YOLO                │                               │
  │  - Confianza                  │                               │
  │  - Complejidad MP             │                               │
  │  - Frame skip                 │                               │
  │                               │                               │
  │  OUTPUT                       │                               │
  │  - Formato (JSON/CSV)         │                               │
  │  - Ruta                       │                               │
  ├──────────────────────────────┴───────────────────────────────┤
  │  [▶ Procesar]  [⏹ Detener]  [📂 Abrir carpeta]              │
  │  ███████████░░░░░░░░░░░░░░░░  45%  ETA 12s                    │
  ├──────────────────────────────────────────────────────────────┤
  │  LOG                                                          │
  │  > Cargando video...                                          │
  │  > Procesando frame 45/100...                                 │
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
    QSizePolicy, QApplication,
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
# WORKER QUE CORRE EN HILO
# ============================================================

class ProcessingWorker(QObject):
    """
    Worker que corre el VideoProcessor en un hilo separado.
    Emite señales para actualizar la UI sin bloquear.
    """
    progress = Signal(int, int, float, float)  # current, total, fps, eta
    finished = Signal(str)                     # error (vacío si OK)
    log_message = Signal(str)

    def __init__(self, plugin, config: Dict[str, Any]):
        super().__init__()
        self._plugin = plugin
        self._config = config

    def run(self):
        """Arranca el procesamiento. Se llama desde QThreadPool o un QThread."""
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

    - Carga video
    - Configura tracker
    - Procesa en background con progreso en vivo
    - Preview del frame actual con landmarks (opcional)
    """

    def __init__(self, plugin, parent=None):
        super().__init__(parent)
        self._plugin = plugin
        self._video_path = ""
        self._output_path = ""
        self._worker_thread: Optional[QThread] = None
        self._worker: Optional[ProcessingWorker] = None
        self._is_processing = False
        self._preview_enabled = True
        self._last_preview_time = 0.0

        self.setWindowTitle("🎬 Motion Capture Studio")
        self.setMinimumSize(1100, 720)
        self.setModal(False)

        self._setup_ui()
        self._connect_signals()
        self._load_plugin_config()

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
        help_btn.setProperty("type", "secondary")
        help_btn.setFixedHeight(30)
        help_btn.clicked.connect(self._show_help)
        title_row.addWidget(help_btn)

        main_layout.addLayout(title_row)

        # === Splitter principal ===
        splitter = QSplitter(Qt.Horizontal)

        # ---------- Columna izquierda: controles ----------
        left = QFrame()
        left.setMinimumWidth(380)
        left.setMaximumWidth(480)
        left_layout = QVBoxLayout(left)
        left_layout.setSpacing(12)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Input
        input_group = QGroupBox("📁 Video de Entrada")
        input_layout = QVBoxLayout(input_group)

        row1 = QHBoxLayout()
        self.video_path_edit = QLineEdit()
        self.video_path_edit.setPlaceholderText("Ruta del video...")
        self.video_path_edit.textChanged.connect(self._on_video_path_changed)
        row1.addWidget(self.video_path_edit, 1)

        browse_btn = QPushButton("📁")
        browse_btn.setFixedWidth(40)
        browse_btn.clicked.connect(self._browse_video)
        row1.addWidget(browse_btn)
        input_layout.addLayout(row1)

        self.video_info_label = QLabel("Sin video seleccionado")
        self.video_info_label.setStyleSheet(
            "color: rgba(255,255,255,0.5); font-size: 11px;"
        )
        self.video_info_label.setWordWrap(True)
        input_layout.addWidget(self.video_info_label)

        left_layout.addWidget(input_group)

        # Tracker
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

        tracker_layout.addWidget(QLabel("Frame skip:"), 3, 0)
        self.frame_skip_spin = QSpinBox()
        self.frame_skip_spin.setRange(1, 10)
        self.frame_skip_spin.setValue(1)
        self.frame_skip_spin.setToolTip(
            "1 = procesar todos los frames\n"
            "2 = procesar 1 de cada 2\n"
            "Útil para videos largos"
        )
        tracker_layout.addWidget(self.frame_skip_spin, 3, 1)

        tracker_layout.addWidget(QLabel("Máx. frames:"), 4, 0)
        self.max_frames_spin = QSpinBox()
        self.max_frames_spin.setRange(0, 100000)
        self.max_frames_spin.setValue(0)
        self.max_frames_spin.setSpecialValueText("Sin límite")
        tracker_layout.addWidget(self.max_frames_spin, 4, 1)

        left_layout.addWidget(tracker_group)

        # Output
        output_group = QGroupBox("💾 Exportación")
        output_layout = QGridLayout(output_group)
        output_layout.setVerticalSpacing(8)
        output_layout.setHorizontalSpacing(12)

        output_layout.addWidget(QLabel("Formato:"), 0, 0)
        self.format_combo = QComboBox()
        self.format_combo.addItems(["JSON", "CSV"])
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

        left_layout.addWidget(output_group)

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
        self.preview_frame.setMinimumHeight(380)
        self.preview_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        pf_layout = QVBoxLayout(self.preview_frame)
        pf_layout.setContentsMargins(8, 8, 8, 8)

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview_label.setStyleSheet(
            "color: rgba(255,255,255,0.4); font-size: 13px; background: transparent;"
        )
        self.preview_label.setText("📼\nCarga un video para previsualizar")
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

        splitter.setSizes([400, 700])
        main_layout.addWidget(splitter, 1)

        # === Barra de acciones ===
        actions = QHBoxLayout()

        self.process_btn = QPushButton("▶ Procesar")
        self.process_btn.setProperty("type", "primary")
        self.process_btn.setMinimumHeight(40)
        self.process_btn.setMinimumWidth(160)
        self.process_btn.clicked.connect(self._on_process_clicked)
        actions.addWidget(self.process_btn)

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

        # === Progreso ===
        progress_row = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setMinimumHeight(20)
        progress_row.addWidget(self.progress_bar, 1)

        self.progress_label = QLabel("Listo")
        self.progress_label.setMinimumWidth(200)
        self.progress_label.setStyleSheet(
            "color: rgba(255,255,255,0.7); font-size: 11px;"
        )
        progress_row.addWidget(self.progress_label)

        main_layout.addLayout(progress_row)

        # === Log ===
        log_group = QGroupBox("📋 Log")
        log_layout = QVBoxLayout(log_group)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(120)
        self.log_text.setPlaceholderText("Los mensajes de procesamiento aparecerán aquí...")
        log_layout.addWidget(self.log_text)

        main_layout.addWidget(log_group)

    def _connect_signals(self):
        """Conecta señales internas."""
        pass

    # ==================== CONFIG ====================

    def _load_plugin_config(self):
        """Carga la config guardada del plugin (si existe)."""
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
        except Exception as e:
            logger.debug(f"No se pudo cargar config: {e}")

    def _save_plugin_config(self):
        """Guarda la config actual del diálogo."""
        try:
            if self._plugin.context.settings is not None:
                cfg = {
                    "yolo_model_idx": self.yolo_model_combo.currentIndex(),
                    "yolo_conf": self.yolo_conf_spin.value(),
                    "mp_complexity_idx": self.mp_complexity_combo.currentIndex(),
                    "frame_skip": self.frame_skip_spin.value(),
                    "max_frames": self.max_frames_spin.value(),
                    "format": self.format_combo.currentText(),
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
        """Cuando cambia la ruta del video, actualiza info y autogenera salida."""
        self._video_path = path.strip()

        if not self._video_path or not os.path.isfile(self._video_path):
            self.video_info_label.setText("Sin video seleccionado")
            self.preview_label.setText("📼\nCarga un video para previsualizar")
            return

        # Info del video
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
                self._log(f"Video cargado: {os.path.basename(self._video_path)}")
                self._log(f"  {info}")

                # Mostrar primer frame como preview
                ret, frame = cap.read()
                if ret:
                    self._show_preview_frame(frame, [])
                cap.release()
            else:
                self.video_info_label.setText("⚠️ No se pudo abrir el video")
        except Exception as e:
            self.video_info_label.setText(f"⚠️ Error: {e}")

        # Autogenerar salida
        base = os.path.splitext(self._video_path)[0]
        fmt = self.format_combo.currentText().lower()
        default_output = f"{base}_mocap.{fmt}"
        self.output_path_edit.setText(default_output)
        self._output_path = default_output

    def _on_format_changed(self, fmt: str):
        """Cuando cambia el formato, actualiza la extensión del archivo de salida."""
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
        """
        Muestra un frame con bounding boxes y landmarks dibujados.

        Args:
            frame_bgr: np.ndarray BGR
            persons: List[PersonDetection] (opcional)
        """
        try:
            import cv2
            import numpy as np

            # Copia para dibujar
            vis = frame_bgr.copy()

            if self._preview_enabled and persons:
                for person in persons:
                    # Bounding box
                    x, y, w, h = person.bbox
                    cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 255, 0), 2)

                    # Track ID
                    label = f"ID {person.track_id}  {person.confidence:.2f}"
                    cv2.putText(
                        vis, label, (x, max(20, y - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1,
                    )

                    # Landmarks
                    if person.landmarks:
                        self._draw_landmarks(vis, person.landmarks, x, y, w, h)

            # Convertir BGR → RGB → QImage
            rgb = cv2.cvtColor(vis, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            bytes_per_line = ch * w
            qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)

            # Escalar al tamaño del label
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
        """Dibuja los 33 landmarks de MediaPipe sobre el frame."""
        try:
            import cv2

            # Conexiones estándar de MediaPipe Pose (33 landmarks)
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

            # Puntos (landmarks normalizados al bbox)
            points = []
            for lm in landmarks:
                nx, ny, _, vis_ = lm
                # Los landmarks están normalizados al crop; los convertimos al frame
                # Como crop = bbox + padding, aproximamos así:
                px = int(bbox_x + nx * bbox_w)
                py = int(bbox_y + ny * bbox_h)
                points.append((px, py, vis_))

            # Dibujar conexiones
            for a, b in CONNECTIONS:
                if a < len(points) and b < len(points):
                    pa = points[a]
                    pb = points[b]
                    if pa[2] > 0.3 and pb[2] > 0.3:
                        cv2.line(vis, (pa[0], pa[1]), (pb[0], pb[1]),
                                 (0, 255, 255), 2)

            # Dibujar puntos
            for px, py, vis_ in points:
                if vis_ > 0.3:
                    cv2.circle(vis, (px, py), 3, (255, 0, 255), -1)
        except Exception as e:
            logger.debug(f"Error dibujando landmarks: {e}")

    # ==================== PROCESAMIENTO ====================

    def _on_process_clicked(self):
        """Valida y arranca el procesamiento."""
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

        # Verificar que el plugin tenga el tracker cargado
        if self._plugin._tracker is None:
            QMessageBox.warning(
                self, "Error",
                "El tracker no está cargado.\n\n"
                "Instala las dependencias:\n"
                "  pip install ultralytics mediapipe opencv-python\n\n"
                "Luego reinicia la aplicación."
            )
            return

        # Config final
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

        # Guardar config
        self._save_plugin_config()

        self._is_processing = True
        self._output_path = output_path
        self.process_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.open_folder_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_label.setText("Iniciando...")
        self._log(f"▶ Iniciando procesamiento: {os.path.basename(video_path)}")
        self._log(f"   YOLO: {config['yolo_model']} (conf={config['yolo_conf']})")
        self._log(f"   MediaPipe complexity: {config['mp_complexity']}")
        self._log(f"   Frame skip: {config['frame_skip']}")
        self._log(f"   Salida: {output_path}")

        # Crear worker y thread
        self._worker = ProcessingWorker(self._plugin, config)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_processing_finished)
        self._worker.log_message.connect(self._log)

        self._worker_thread = QThread()
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)
        self._worker_thread.start()

    def _on_stop_clicked(self):
        """Solicita detener el procesamiento."""
        if not self._is_processing:
            return
        self._log("⏹ Detención solicitada...")
        self.progress_label.setText("Deteniendo...")
        self._plugin.stop_processing()

    def _on_progress(self, current: int, total: int, fps: float, eta: float):
        """Actualiza la barra de progreso."""
        if total <= 0:
            return
        percent = int((current / total) * 100)
        self.progress_bar.setValue(percent)
        self.progress_label.setText(
            f"Frame {current}/{total}  •  {fps:.1f} fps  •  "
            f"ETA {format_time(eta)}"
        )

    def _on_processing_finished(self, error: str):
        """Cuando el procesamiento termina (con o sin error)."""
        self._is_processing = False
        self.process_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

        # Detener thread
        if self._worker_thread is not None:
            self._worker_thread.quit()
            self._worker_thread.wait(2000)
            self._worker_thread = None
        self._worker = None

        if error:
            self._log(f"❌ Error: {error}")
            self.progress_label.setText(f"❌ Error")
            QMessageBox.critical(self, "Error", error)
        else:
            self.progress_bar.setValue(100)
            self.progress_label.setText("✅ Completado")
            self._log(f"✅ Procesamiento completado")
            self._log(f"   Archivo: {self._output_path}")
            self.open_folder_btn.setEnabled(True)

            if self.open_output_check.isChecked():
                self._open_output_folder()

            QMessageBox.information(
                self, "Éxito",
                f"Captura exportada a:\n{self._output_path}"
            )

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

    # ==================== UTILIDADES ====================

    def _log(self, msg: str):
        """Añade un mensaje al log."""
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {msg}")
        logger.debug(msg)

    def _show_help(self):
        QMessageBox.information(
            self, "🎬 Motion Capture Studio — Ayuda",
            "Este diálogo te permite:\n\n"
            "1. Cargar un fragmento de video\n"
            "2. Configurar el tracker híbrido (YOLO + MediaPipe)\n"
            "3. Procesar el video para extraer landmarks\n"
            "4. Exportar a JSON o CSV\n\n"
            "Flujo:\n"
            "  Video → YOLO detecta personas → MediaPipe extrae 33\n"
            "  landmarks por persona → exportación.\n\n"
            "Recomendaciones:\n"
            "  • Para PC de bajos recursos: usa 'yolov8n-pose.pt' y\n"
            "    'Lite' en MediaPipe. Aumenta 'Frame skip' a 2-3.\n"
            "  • Para máxima precisión: usa 'yolov8m-pose.pt' y 'Heavy'.\n\n"
            "Formatos de video: .mp4, .mkv, .avi, .mov, .webm.\n"
            "Los modelos YOLO y MediaPipe se descargan la primera vez\n"
            "que se usan (requiere internet)."
        )

    # ==================== CIERRE ====================

    def closeEvent(self, event):
        """Al cerrar, detener cualquier procesamiento en curso."""
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