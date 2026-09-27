"""
Visor de video con controles completos + AUDIO.
Usa QMediaPlayer + QVideoWidget de Qt6 (backend nativo del SO).
"""
import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QComboBox, QFrame, QSizePolicy, QScrollArea,
    QMessageBox, QStyle
)
from PySide6.QtCore import Qt, Signal, QUrl, QTimer
from PySide6.QtGui import QKeyEvent, QPixmap, QImage
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

from utils.logger import get_logger

logger = get_logger("VideoPreview")


class VideoPreview(QWidget):
    """
    Reproductor de video con audio, controles completos y zoom.
    Usa QMediaPlayer (backend nativo).
    """

    closed = Signal()

    SPEEDS = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0]

    def __init__(self, parent=None):
        super().__init__(parent)

        self._current_path = None
        self._duration_ms = 0
        self._position_ms = 0
        self._is_seeking = False
        self._zoom = 1.0

        self._setup_ui()
        self._setup_player()
        self.hide()

    # ==================== UI ====================

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # ===== Toolbar superior =====
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(28, 28)
        self.close_btn.setToolTip("Cerrar (Esc)")
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #999;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover { color: #f44336; }
        """)
        self.close_btn.clicked.connect(self.close_video)
        toolbar.addWidget(self.close_btn)

        self.file_label = QLabel("Sin video")
        self.file_label.setStyleSheet("color: #888; font-weight: 600;")
        self.file_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(self.file_label)

        toolbar.addStretch()

        self.info_label = QLabel("")
        self.info_label.setStyleSheet("color: #666; font-size: 11px;")
        toolbar.addWidget(self.info_label)

        layout.addLayout(toolbar)

        # ===== Área de video =====
        video_container = QFrame()
        video_container.setStyleSheet("""
            QFrame {
                background-color: #000000;
                border: 1px solid #303030;
                border-radius: 6px;
            }
        """)
        video_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        video_container.setMinimumHeight(300)

        vc_layout = QVBoxLayout(video_container)
        vc_layout.setContentsMargins(0, 0, 0, 0)

        self.video_widget = QVideoWidget()
        self.video_widget.setStyleSheet("background: #000;")
        vc_layout.addWidget(self.video_widget)

        layout.addWidget(video_container, 1)

        # ===== Controles inferiores =====
        controls = QFrame()
        controls.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a1a2e, stop:1 #0d1445);
                border: 1px solid #303030;
                border-radius: 6px;
            }
        """)

        c_layout = QVBoxLayout(controls)
        c_layout.setContentsMargins(10, 8, 10, 8)
        c_layout.setSpacing(6)

        # --- Fila 1: Slider de progreso ---
        progress_row = QHBoxLayout()
        progress_row.setSpacing(8)

        self.current_time_label = QLabel("00:00")
        self.current_time_label.setStyleSheet(
            "color: #4da0c4; font-weight: bold; font-family: monospace; font-size: 12px;"
        )
        self.current_time_label.setFixedWidth(55)
        self.current_time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        progress_row.addWidget(self.current_time_label)

        self.progress_slider = QSlider(Qt.Horizontal)
        self.progress_slider.setRange(0, 1000)
        self.progress_slider.setValue(0)
        self.progress_slider.sliderPressed.connect(self._on_seek_start)
        self.progress_slider.sliderReleased.connect(self._on_seek_end)
        self.progress_slider.sliderMoved.connect(self._on_seek_move)
        self.progress_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: rgba(255,255,255,0.1);
                height: 6px;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4da0c4, stop:1 #6a1b9a);
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                width: 14px;
                height: 14px;
                border-radius: 7px;
                margin: -4px 0;
                border: 2px solid #4da0c4;
            }
            QSlider::handle:horizontal:hover {
                background: #4da0c4;
                border-color: #ffffff;
            }
        """)
        progress_row.addWidget(self.progress_slider, 1)

        self.total_time_label = QLabel("00:00")
        self.total_time_label.setStyleSheet(
            "color: #4da0c4; font-weight: bold; font-family: monospace; font-size: 12px;"
        )
        self.total_time_label.setFixedWidth(55)
        progress_row.addWidget(self.total_time_label)

        c_layout.addLayout(progress_row)

        # --- Fila 2: Botones de control ---
        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(6)

        # Play/Pause
        self.play_btn = QPushButton("▶")
        self.play_btn.setFixedSize(40, 32)
        self.play_btn.setToolTip("Reproducir/Pausar (Espacio)")
        self.play_btn.clicked.connect(self._toggle_play)
        self.play_btn.setStyleSheet(self._get_control_button_style("#2e7d32"))
        buttons_row.addWidget(self.play_btn)

        # Stop
        self.stop_btn = QPushButton("⏹")
        self.stop_btn.setFixedSize(32, 32)
        self.stop_btn.setToolTip("Detener")
        self.stop_btn.clicked.connect(self._stop)
        self.stop_btn.setStyleSheet(self._get_control_button_style("#c62828"))
        buttons_row.addWidget(self.stop_btn)

        buttons_row.addSpacing(10)

        # Retroceder 30s
        self.back30_btn = QPushButton("⏪")
        self.back30_btn.setFixedSize(32, 32)
        self.back30_btn.setToolTip("Retroceder 30s (Shift+←)")
        self.back30_btn.clicked.connect(lambda: self._seek_relative(-30))
        self.back30_btn.setStyleSheet(self._get_control_button_style("#444"))
        buttons_row.addWidget(self.back30_btn)

        # Retroceder 5s
        self.back5_btn = QPushButton("◀◀")
        self.back5_btn.setFixedSize(32, 32)
        self.back5_btn.setToolTip("Retroceder 5s (←)")
        self.back5_btn.clicked.connect(lambda: self._seek_relative(-5))
        self.back5_btn.setStyleSheet(self._get_control_button_style("#444"))
        buttons_row.addWidget(self.back5_btn)

        # Frame anterior
        self.prev_frame_btn = QPushButton("⏮")
        self.prev_frame_btn.setFixedSize(32, 32)
        self.prev_frame_btn.setToolTip("Frame anterior (, o k)")
        self.prev_frame_btn.clicked.connect(self._step_backward)
        self.prev_frame_btn.setStyleSheet(self._get_control_button_style("#333"))
        buttons_row.addWidget(self.prev_frame_btn)

        # Frame siguiente
        self.next_frame_btn = QPushButton("⏭")
        self.next_frame_btn.setFixedSize(32, 32)
        self.next_frame_btn.setToolTip("Frame siguiente (. o l)")
        self.next_frame_btn.clicked.connect(self._step_forward)
        self.next_frame_btn.setStyleSheet(self._get_control_button_style("#333"))
        buttons_row.addWidget(self.next_frame_btn)

        # Avanzar 5s
        self.fwd5_btn = QPushButton("▶▶")
        self.fwd5_btn.setFixedSize(32, 32)
        self.fwd5_btn.setToolTip("Avanzar 5s (→)")
        self.fwd5_btn.clicked.connect(lambda: self._seek_relative(5))
        self.fwd5_btn.setStyleSheet(self._get_control_button_style("#444"))
        buttons_row.addWidget(self.fwd5_btn)

        # Avanzar 30s
        self.fwd30_btn = QPushButton("⏩")
        self.fwd30_btn.setFixedSize(32, 32)
        self.fwd30_btn.setToolTip("Avanzar 30s (Shift+→)")
        self.fwd30_btn.clicked.connect(lambda: self._seek_relative(30))
        self.fwd30_btn.setStyleSheet(self._get_control_button_style("#444"))
        buttons_row.addWidget(self.fwd30_btn)

        buttons_row.addSpacing(10)

        # Velocidad
        speed_label = QLabel("Vel:")
        speed_label.setStyleSheet("color: #aaa; font-size: 11px;")
        buttons_row.addWidget(speed_label)

        self.speed_combo = QComboBox()
        for sp in self.SPEEDS:
            self.speed_combo.addItem(f"{sp}x", sp)
        self.speed_combo.setCurrentText("1.0x")
        self.speed_combo.setFixedWidth(70)
        self.speed_combo.currentIndexChanged.connect(self._on_speed_changed)
        self.speed_combo.setStyleSheet("""
            QComboBox {
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 4px;
                padding: 4px 8px;
                color: white;
                font-size: 11px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background: #1a237e;
                color: white;
                selection-background-color: #4a148c;
            }
        """)
        buttons_row.addWidget(self.speed_combo)

        buttons_row.addSpacing(10)

        # Volumen (NUEVO)
        vol_label = QLabel("🔊")
        vol_label.setStyleSheet("color: #aaa; font-size: 13px;")
        buttons_row.addWidget(vol_label)

        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.setFixedWidth(100)
        self.volume_slider.setToolTip("Volumen (↑/↓)")
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        self.volume_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: rgba(255,255,255,0.1);
                height: 4px;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4da0c4, stop:1 #6a1b9a);
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                width: 12px;
                height: 12px;
                border-radius: 6px;
                margin: -4px 0;
                border: 2px solid #4da0c4;
            }
        """)
        buttons_row.addWidget(self.volume_slider)

        self.volume_label = QLabel("70%")
        self.volume_label.setStyleSheet(
            "color: #4da0c4; font-weight: bold; font-size: 11px;"
        )
        self.volume_label.setFixedWidth(35)
        self.volume_label.setAlignment(Qt.AlignCenter)
        buttons_row.addWidget(self.volume_label)

        buttons_row.addStretch()

        # Botón mute
        self.mute_btn = QPushButton("🔇")
        self.mute_btn.setFixedSize(32, 32)
        self.mute_btn.setToolTip("Silenciar (M)")
        self.mute_btn.setCheckable(True)
        self.mute_btn.clicked.connect(self._toggle_mute)
        self.mute_btn.setStyleSheet(self._get_control_button_style("#333"))
        buttons_row.addWidget(self.mute_btn)

        # Zoom
        zoom_out_btn = QPushButton("🔍−")
        zoom_out_btn.setFixedSize(36, 32)
        zoom_out_btn.setToolTip("Reducir zoom (Ctrl+-)")
        zoom_out_btn.clicked.connect(self._zoom_out)
        zoom_out_btn.setStyleSheet(self._get_control_button_style("#333"))
        buttons_row.addWidget(zoom_out_btn)

        self.zoom_label = QLabel("100%")
        self.zoom_label.setStyleSheet(
            "color: #4da0c4; font-weight: bold; font-size: 11px;"
        )
        self.zoom_label.setFixedWidth(45)
        self.zoom_label.setAlignment(Qt.AlignCenter)
        buttons_row.addWidget(self.zoom_label)

        zoom_in_btn = QPushButton("🔍+")
        zoom_in_btn.setFixedSize(36, 32)
        zoom_in_btn.setToolTip("Aumentar zoom (Ctrl++)")
        zoom_in_btn.clicked.connect(self._zoom_in)
        zoom_in_btn.setStyleSheet(self._get_control_button_style("#333"))
        buttons_row.addWidget(zoom_in_btn)

        zoom_fit_btn = QPushButton("⛶")
        zoom_fit_btn.setFixedSize(36, 32)
        zoom_fit_btn.setToolTip("Ajustar a ventana (Ctrl+0)")
        zoom_fit_btn.clicked.connect(self._zoom_fit)
        zoom_fit_btn.setStyleSheet(self._get_control_button_style("#333"))
        buttons_row.addWidget(zoom_fit_btn)

        c_layout.addLayout(buttons_row)

        layout.addWidget(controls)

        self._set_controls_enabled(False)

    def _get_control_button_style(self, bg_color: str) -> str:
        """
        Genera el estilo para un botón de control.
        Acepta colores de 3 o 6 dígitos y los normaliza a 6.
        Usa rgba() para hover/pressed para evitar problemas de sintaxis.
        """
        def normalize_hex(hex_color: str) -> str:
            """Convierte '#444' o '#444444' a '#444444'"""
            h = hex_color.lstrip("#")
            if len(h) == 3:
                h = "".join([c * 2 for c in h])
            return f"#{h}"

        def hex_to_rgb(hex_color: str):
            """Convierte '#444444' a (68, 68, 68)"""
            h = hex_color.lstrip("#")
            if len(h) == 3:
                h = "".join([c * 2 for c in h])
            try:
                return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
            except (ValueError, IndexError):
                return (68, 68, 68)

        bg_normalized = normalize_hex(bg_color)
        r, g, b = hex_to_rgb(bg_normalized)

        return f"""
            QPushButton {{
                background: {bg_normalized};
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 6px;
                color: #ffffff;
                font-size: 18px;
                font-weight: 600;
                font-family: "Segoe UI Emoji", "Segoe UI Symbol", "Noto Color Emoji", sans-serif;
                padding: 0px;
            }}
            QPushButton:hover {{
                background: rgba({r}, {g}, {b}, 0.85);
                border-color: rgba(255, 255, 255, 0.55);
            }}
            QPushButton:pressed {{
                background: rgba({r}, {g}, {b}, 0.6);
            }}
            QPushButton:disabled {{
                background: #2a2a2a;
                color: #555555;
                border-color: #3a3a3a;
            }}
            QPushButton:checked {{
                background: #f44336;
                border-color: #ff6659;
                color: #ffffff;
            }}
    """

    def _set_controls_enabled(self, enabled: bool):
        for w in [
            self.play_btn, self.stop_btn,
            self.back30_btn, self.back5_btn, self.prev_frame_btn,
            self.next_frame_btn, self.fwd5_btn, self.fwd30_btn,
            self.speed_combo, self.progress_slider,
            self.volume_slider, self.mute_btn
        ]:
            w.setEnabled(enabled)

    # ==================== PLAYER SETUP ====================

    def _setup_player(self):
        from utils.config_loader import advanced_config
        default_vol = advanced_config.get("video_default_volume", 0.7)

        self._audio_output = QAudioOutput()
        self._audio_output.setVolume(default_vol)  # ← NUEVO

        # Media player
        self._player = QMediaPlayer()
        self._player.setVideoOutput(self.video_widget)
        self._player.setAudioOutput(self._audio_output)

        # Conectar señales
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_state_changed)
        self._player.errorOccurred.connect(self._on_error)
        self._player.mediaStatusChanged.connect(self._on_media_status_changed)

        logger.info("🎬 QMediaPlayer configurado con audio")

    # ==================== CARGA DE VIDEO ====================

    def load_video(self, video_path: str):
        """Carga un video y comienza a reproducirlo"""
        if not os.path.exists(video_path):
            logger.error(f"Video no encontrado: {video_path}")
            return

        self._current_path = video_path
        self.file_label.setText(os.path.basename(video_path))

        # Reset UI
        self.progress_slider.setValue(0)
        self.current_time_label.setText("00:00")
        self.total_time_label.setText("00:00")
        self.info_label.setText("")

        # Cargar
        self._player.setSource(QUrl.fromLocalFile(video_path))
        self._player.play()

        self.show()
        self.raise_()
        self._set_controls_enabled(True)

        logger.info(f"🎬 Video cargado: {os.path.basename(video_path)}")

        # Actualizar info cuando esté listo
        QTimer.singleShot(300, self._update_video_info)

    def _update_video_info(self):
        """Actualiza info del video (resolución, etc.)"""
        if not self._player or not self._current_path:
            return

        try:
            # Obtener metadata del media
            w = self.video_widget.width()
            h = self.video_widget.height()

            # Obtener resolución real del video
            meta = self._player.metaData()
            resolution = meta.value("Resolution")

            if resolution:
                # Puede ser QSize o string
                try:
                    res_str = f"{resolution.width()}x{resolution.height()}"
                except AttributeError:
                    res_str = str(resolution)
            else:
                res_str = ""

            duration_ms = self._player.duration()
            if duration_ms > 0:
                self.info_label.setText(
                    f"{res_str} | Duración: {self._format_time(duration_ms)}"
                )
                self.total_time_label.setText(self._format_time(duration_ms))
                self._duration_ms = duration_ms
        except Exception as e:
            logger.debug(f"Error leyendo metadata: {e}")

    # ==================== CALLBACKS DEL PLAYER ====================

    def _on_position_changed(self, pos_ms: int):
        """Actualiza el slider y el tiempo actual"""
        self._position_ms = pos_ms

        if not self._is_seeking and self._duration_ms > 0:
            slider_val = int((pos_ms / self._duration_ms) * 1000)
            self.progress_slider.blockSignals(True)
            self.progress_slider.setValue(slider_val)
            self.progress_slider.blockSignals(False)

        self.current_time_label.setText(self._format_time(pos_ms))

    def _on_duration_changed(self, duration_ms: int):
        """Actualiza la duración total"""
        self._duration_ms = duration_ms
        self.total_time_label.setText(self._format_time(duration_ms))

    def _on_state_changed(self, state):
        """Actualiza el botón play/pause"""
        if state == QMediaPlayer.PlayingState:
            self.play_btn.setText("⏸")
            self.play_btn.setToolTip("Pausar (Espacio)")
        elif state == QMediaPlayer.PausedState:
            self.play_btn.setText("▶")
            self.play_btn.setToolTip("Reproducir (Espacio)")
        else:  # StoppedState
            self.play_btn.setText("▶")
            self.play_btn.setToolTip("Reproducir (Espacio)")

    def _on_media_status_changed(self, status):
        """Maneja cambios de estado del media"""
        if status == QMediaPlayer.EndOfMedia:
            # Al terminar, volver al inicio
            self._player.setPosition(0)
            self._player.pause()
            logger.debug("Video terminado")
        elif status == QMediaPlayer.LoadedMedia:
            # Cuando ya está cargado, actualizar duración
            self._on_duration_changed(self._player.duration())
        elif status == QMediaPlayer.InvalidMedia:
            self._on_error(
                QMediaPlayer.Error.InvalidMedia,
                "Formato de video no soportado o archivo corrupto"
            )

    def _on_error(self, error, error_string: str):
        """Muestra errores del player"""
        logger.error(f"Error del reproductor: {error} - {error_string}")
        self.info_label.setText(f"⚠️ {error_string}")
        self.info_label.setStyleSheet("color: #f44336; font-size: 11px;")

    # ==================== ACCIONES DE USUARIO ====================

    def _toggle_play(self):
        if not self._player:
            return

        if self._player.playbackState() == QMediaPlayer.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _stop(self):
        if not self._player:
            return
        self._player.stop()
        self._player.setPosition(0)

    def _seek_relative(self, seconds: float):
        """Salta N segundos adelante o atrás"""
        if not self._player:
            return
        delta_ms = int(seconds * 1000)
        new_pos = max(0, min(self._player.position() + delta_ms,
                             self._duration_ms))
        self._player.setPosition(new_pos)

    def _step_forward(self):
        """Avanza ~1 frame (asumiendo 30 fps → 33ms)"""
        from utils.config_loader import advanced_config
        step_ms = advanced_config.get("step_frame_ms", 33)
        if not self._player:
            return
        self._player.pause()
        new_pos = self._player.position() + step_ms
        self._player.setPosition(min(new_pos, self._duration_ms))

    def _step_backward(self):
        """Retrocede ~1 frame"""
        if not self._player:
            return
        self._player.pause()
        new_pos = max(0, self._player.position() - 33)
        self._player.setPosition(new_pos)

    def _on_seek_start(self):
        self._is_seeking = True

    def _on_seek_move(self, value: int):
        """Muestra preview del tiempo mientras se arrastra"""
        if self._duration_ms > 0:
            preview_ms = int((value / 1000.0) * self._duration_ms)
            self.current_time_label.setText(self._format_time(preview_ms))

    def _on_seek_end(self):
        """Ejecuta el seek real al soltar"""
        self._is_seeking = False
        if self._player and self._duration_ms > 0:
            target_ms = int((self.progress_slider.value() / 1000.0) * self._duration_ms)
            self._player.setPosition(target_ms)

    def _on_speed_changed(self, index: int):
        if not self._player:
            return
        speed = self.speed_combo.itemData(index)
        if speed is not None:
            self._player.setPlaybackRate(float(speed))
            logger.debug(f"Velocidad: {speed}x")

    def _on_volume_changed(self, value: int):
        """Ajusta el volumen"""
        if self._audio_output:
            self._audio_output.setVolume(value / 100.0)
        self.volume_label.setText(f"{value}%")

        # Actualizar icono del botón mute
        if value == 0:
            self.mute_btn.setChecked(True)
        else:
            self.mute_btn.setChecked(False)

    def _toggle_mute(self, checked: bool):
        """Silencia/desilencia"""
        if not self._audio_output:
            return

        if checked:
            self._audio_output.setMuted(True)
            self.mute_btn.setText("🔇")
            self.mute_btn.setToolTip("Activar sonido (M)")
        else:
            self._audio_output.setMuted(False)
            self.mute_btn.setText("🔊")
            self.mute_btn.setToolTip("Silenciar (M)")

    # ==================== ZOOM ====================

    def _zoom_in(self):
        """Aumenta el tamaño del QVideoWidget (zoom visual)"""
        self._zoom = min(3.0, self._zoom * 1.25)
        self._update_zoom_label()
        self._apply_zoom()

    def _zoom_out(self):
        self._zoom = max(0.3, self._zoom / 1.25)
        self._update_zoom_label()
        self._apply_zoom()

    def _zoom_fit(self):
        self._zoom = 1.0
        self._update_zoom_label()
        self._apply_zoom()

    def _apply_zoom(self):
        """
        Aplica zoom al QVideoWidget cambiando su tamaño mínimo.
        QMediaPlayer escala el video automáticamente al tamaño del widget.
        """
        base_w = 640
        base_h = 360

        target_w = int(base_w * self._zoom)
        target_h = int(base_h * self._zoom)

        self.video_widget.setMinimumSize(target_w, target_h)

    def _update_zoom_label(self):
        self.zoom_label.setText(f"{int(self._zoom * 100)}%")

    # ==================== UTILIDADES ====================

    def _format_time(self, ms: int) -> str:
        seconds = ms // 1000
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    # ==================== EVENTOS ====================

    def close_video(self):
        """Cierra el video y el visor"""
        if self._player:
            try:
                self._player.stop()
                self._player.setSource(QUrl())  # Liberar el archivo
            except Exception as e:
                logger.debug(f"Error deteniendo player: {e}")

        self._current_path = None
        self.file_label.setText("Sin video")
        self.info_label.setText("")
        self.info_label.setStyleSheet("color: #666; font-size: 11px;")
        self.progress_slider.setValue(0)
        self.current_time_label.setText("00:00")
        self.total_time_label.setText("00:00")
        self._duration_ms = 0
        self._set_controls_enabled(False)
        self.hide()
        self.closed.emit()

    def keyPressEvent(self, event: QKeyEvent):
        """Atajos de teclado"""
        if not self._player or not self._current_path:
            super().keyPressEvent(event)
            return
        
        from utils.config_loader import advanced_config
        small = advanced_config.get("seek_step_small", 5)
        big = advanced_config.get("seek_step_big", 30)

        key = event.key()
        mods = event.modifiers()

        # Espacio: Play/Pause
        if key == Qt.Key_Space:
            self._toggle_play()
            return

        # Escape: Cerrar
        if key == Qt.Key_Escape:
            self.close_video()
            return

        # ← / Shift+←
        if key == Qt.Key_Left:
            self._seek_relative(-big  if mods == Qt.ShiftModifier else -small)
            return

        # → / Shift+→
        if key == Qt.Key_Right:
            self._seek_relative(big if mods == Qt.ShiftModifier else small)
            return

        # ↑ / ↓: Volumen
        if key == Qt.Key_Up:
            self.volume_slider.setValue(min(100, self.volume_slider.value() + 5))
            return
        if key == Qt.Key_Down:
            self.volume_slider.setValue(max(0, self.volume_slider.value() - 5))
            return

        # M: Mute
        if key == Qt.Key_M:
            self.mute_btn.setChecked(not self.mute_btn.isChecked())
            self._toggle_mute(self.mute_btn.isChecked())
            return

        # , o K: frame anterior
        if key == Qt.Key_Comma or key == Qt.Key_K:
            self._step_backward()
            return

        # . o L: frame siguiente
        if key == Qt.Key_Period or key == Qt.Key_L:
            self._step_forward()
            return

        # Home / End
        if key == Qt.Key_Home:
            self._player.setPosition(0)
            return
        if key == Qt.Key_End:
            self._player.setPosition(self._duration_ms)
            return

        # Ctrl+0
        if key == Qt.Key_0 and mods == Qt.ControlModifier:
            self._zoom_fit()
            return

        # Ctrl++ / Ctrl+=
        if key in (Qt.Key_Plus, Qt.Key_Equal) and mods == Qt.ControlModifier:
            self._zoom_in()
            return

        # Ctrl+-
        if key == Qt.Key_Minus and mods == Qt.ControlModifier:
            self._zoom_out()
            return

        super().keyPressEvent(event)

    def closeEvent(self, event):
        """Liberar recursos al cerrar"""
        if self._player:
            self._player.stop()
        super().closeEvent(event)