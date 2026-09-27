"""
Widget de cámara individual - v4
- Botón mute independiente
- Pregunta al grabar sin audio
- Logs DEBUG integrados
"""
from PySide6.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QFrame, QSizePolicy, QMessageBox, QWidget)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve, QRect, QSize
from PySide6.QtGui import QPixmap, QImage, QMouseEvent

from core.models import CameraDevice, CameraStatus
from utils.timer_manager import timer_manager
from utils.pixmap_pool import ScaledPixmapPool
from utils.logger import get_logger

logger = get_logger("CameraWidget")


class CameraWidget(QFrame):
    """Widget que muestra el feed de una cámara"""

    capture_requested = Signal(int)
    recording_toggled = Signal(int, bool)
    camera_removed = Signal(int)
    toggle_expand_requested = Signal(int)
    flash_toggled = Signal(int, bool)
    auto_flash_toggled = Signal(int, bool)
    expand_finished = Signal()
    selection_changed = Signal(int, bool)
    audio_state_changed = Signal(int, bool)   # ✅ NUEVO: (camera_id, muted)

    def __init__(self, camera: CameraDevice, parent=None):
        super().__init__(parent)
        self.camera = camera
        self._tm = timer_manager

        from utils.config_loader import advanced_config
        cfg = advanced_config.get_all()

        # Tamaños
        self.setMinimumSize(
            cfg.get("camera_widget_min_width", 320),
            cfg.get("camera_widget_min_height", 280)
        )
        self.setMaximumSize(
            cfg.get("camera_widget_max_width", 480),
            cfg.get("camera_widget_max_height", 400)
        )

        self._fps_check_interval = cfg.get("camera_fps_check_interval", 1000)
        self._recording_update_interval = cfg.get("recording_update_interval", 1000)

        self.is_recording = False
        self.is_paused = False
        self.is_expanded = False
        self._is_selected = False
        self.flash_active = False
        self.auto_flash_enabled = camera.auto_flash

        # Estado de frames
        self._fps_counter = 0
        self._last_frame = None
        self._paused_frame = None
        self._pending_frame = None
        self._last_display_time = 0
        self._min_display_interval = int(1000 / cfg.get("camera_display_fps", 30))
        self._run_update_audio_level = False

        # Pool + control del timer display
        self._pixmap_pool = ScaledPixmapPool(size=cfg.get("pixmap_pool_size", 3))
        self._display_timer_running = False
        self._empty_cycles = 0

        # Grabación
        self.recording_time = 0

        # Animación de expansión
        self.expand_animation = QPropertyAnimation(self, b"geometry")
        self.expand_animation.setDuration(cfg.get("anim_duration_ms", 350))
        self.expand_animation.setEasingCurve(QEasingCurve.InOutQuad)
        self.expand_animation.finished.connect(self._on_animation_finished)
        self._animating = False
        self._target_geometry = None
        self._original_geometry = None

        # Nombres de timers
        self._owner = f"camera_{camera.id}"
        self.audio_level_timer_name = f"{self._owner}.audio_level"
        self._fps_timer_group_name = "fps"

        # 🔍 DEBUG: Estado inicial
        logger.debug(
            f"🔧 [init] CameraWidget: name={camera.name}, id={camera.id}, "
            f"min={cfg.get('camera_widget_min_width', 320)}x"
            f"{cfg.get('camera_widget_min_height', 280)}, "
            f"max={cfg.get('camera_widget_max_width', 480)}x"
            f"{cfg.get('camera_widget_max_height', 400)}, "
            f"fps_display={cfg.get('camera_display_fps', 30)}, "
            f"pixmap_pool={cfg.get('pixmap_pool_size', 3)}"
        )

        self._setup_ui()
        self._apply_status_style(CameraStatus.DISCONNECTED)
        self._update_selection_style()

        # Solo FPS timer al inicio
        self._tm.create_group(self._owner, [
            (self._fps_timer_group_name, self._fps_check_interval, self._update_fps, False),
        ])

        # ✅ FIX: crear el timer display SIN arrancarlo
        self._tm.create(
            f"{self._owner}.display",
            33,
            self._process_pending_frame,
            start=False
        )
        logger.debug(
            f"🔧 [init] {self.camera.name}: timer display creado (inactivo, 33ms)"
        )

    def _setup_ui(self):
        self.setObjectName("CameraWidget")
        self.setMinimumSize(320, 280)
        self.setMaximumSize(480, 400)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        # Header
        header_layout = QHBoxLayout()

        self.name_label = QLabel(self.camera.name)
        self.name_label.setObjectName("cameraName")
        self.name_label.setProperty("type", "title")
        header_layout.addWidget(self.name_label)

        header_layout.addStretch()

        self.selection_indicator = QLabel("")
        self.selection_indicator.setStyleSheet(
            "color: #4CAF50; font-size: 13px; font-weight: bold;"
        )
        header_layout.addWidget(self.selection_indicator)

        # Los plugins añaden sus botones aquí (flash, audio, etc.)
        self._header_layout_ref = header_layout
        self._apply_extension_widgets(header_layout)

        self.status_label = QLabel("● Desconectado")
        self.status_label.setObjectName("cameraStatus")
        header_layout.addWidget(self.status_label)

        self.pause_btn = QPushButton("⏸")
        self.pause_btn.setFixedSize(28, 28)
        self.pause_btn.setToolTip("Pausar/Reanudar video")
        self.pause_btn.setStyleSheet(self._get_icon_button_style())
        self.pause_btn.clicked.connect(self._toggle_pause)
        header_layout.addWidget(self.pause_btn)

        self.remove_btn = QPushButton("❌")
        self.remove_btn.setFixedSize(28, 28)
        self.remove_btn.setToolTip("Eliminar cámara")
        self.remove_btn.setStyleSheet(self._get_icon_button_style())
        self.remove_btn.clicked.connect(
            lambda: self.camera_removed.emit(self.camera.id)
        )
        header_layout.addWidget(self.remove_btn)

        layout.addLayout(header_layout)

        # Área de video
        self.video_frame = QFrame()
        self.video_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(0, 0, 0, 0.5);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 14px;
            }
        """)
        self.video_frame.setMinimumHeight(200)
        self.video_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.video_frame.mouseDoubleClickEvent = self._on_double_click
        self.video_frame.mousePressEvent = self._on_mouse_press

        video_layout = QVBoxLayout(self.video_frame)
        video_layout.setContentsMargins(2, 2, 2, 2)

        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet("""
            color: rgba(255,255,255,0.4);
            font-size: 14px;
            background: transparent;
            border-radius: 12px;
        """)
        self.video_label.setText("📷\nConectando...")
        self.video_label.mouseDoubleClickEvent = self._on_double_click
        self.video_label.mousePressEvent = self._on_mouse_press
        video_layout.addWidget(self.video_label)

        layout.addWidget(self.video_frame)

        # Info
        info_layout = QHBoxLayout()

        if self.camera.is_screen:
            info_text = "🖥️ Captura de pantalla"
        elif self.camera.is_local:
            info_text = f"📹 Cámara índice {self.camera.camera_index}"
        else:
            info_text = f"IP: {self.camera.ip}:{self.camera.port}"

        self.ip_label = QLabel(info_text)
        self.ip_label.setObjectName("cameraInfo")
        info_layout.addWidget(self.ip_label)
        info_layout.addStretch()

        self.pause_indicator = QLabel("")
        self.pause_indicator.setObjectName("cameraPause")
        info_layout.addWidget(self.pause_indicator)

        self.fps_label = QLabel("FPS: 0")
        self.fps_label.setObjectName("cameraFps")
        info_layout.addWidget(self.fps_label)

        layout.addLayout(info_layout)

        # Controles
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(10)

        self.capture_btn = QPushButton("📸 Capturar")
        self.capture_btn.setProperty("type", "capture")
        self.capture_btn.clicked.connect(
            lambda: self.capture_requested.emit(self.camera.id)
        )
        controls_layout.addWidget(self.capture_btn)

        self.record_btn = QPushButton("🎬 Grabar")
        self.record_btn.setProperty("type", "success")
        self.record_btn.clicked.connect(self._toggle_recording)
        controls_layout.addWidget(self.record_btn)

        layout.addLayout(controls_layout)

        self._apply_base_style()

    def _get_icon_button_style(self):
        return """
            QPushButton {
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 14px;
                padding: 0px;
            }
            QPushButton:hover {
                background: rgba(255,152,0,0.15);
                border-color: rgba(255,152,0,0.4);
            }
            QPushButton[type="paused"] {
                background: rgba(255, 152, 0, 0.3);
                border-color: #FF9800;
            }
        """

    def _apply_base_style(self):
        self.setStyleSheet("""
            CameraWidget {
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 20px;
            }
            CameraWidget:hover {
                background: #e8eaf6;
                border-color: rgba(255, 255, 255, 0.4);
            }
            QLabel#cameraName { color: #ffffff; font-weight: bold; font-size: 14px; }
            QLabel#cameraInfo { color: rgba(255,255,255,0.5); font-size: 11px; }
            QLabel#cameraFps { color: rgba(255,255,255,0.5); font-size: 11px; }
            QLabel#cameraPause { color: #FF9800; font-size: 11px; font-weight: bold; }
            QLabel#cameraStatus { font-size: 11px; }
            CameraWidget:hover QLabel#cameraName { color: #1a1a2e; }
            CameraWidget:hover QLabel#cameraInfo { color: rgba(0,0,0,0.6); }
            CameraWidget:hover QLabel#cameraFps { color: rgba(0,0,0,0.6); }
            CameraWidget:hover QLabel#cameraPause { color: #e65100; }
            QPushButton {
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 14px;
                padding: 0px;
            }
            QPushButton:hover {
                background: rgba(0,0,0,0.1);
                border-color: rgba(0,0,0,0.3);
            }
            QPushButton[type="capture"] {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1565c0, stop:0.5 #4a148c, stop:1 #1565c0);
                color: white;
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 50px;
                padding: 8px 16px;
                font-weight: 600;
            }
            QPushButton[type="capture"]:hover {
                border-color: rgba(255,255,255,0.5);
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1e88e5, stop:0.5 #6a1b9a, stop:1 #1e88e5);
            }
            QPushButton[type="success"] {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2e7d32, stop:1 #43a047);
                color: white;
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 50px;
                padding: 8px 16px;
                font-weight: 600;
            }
            QPushButton[type="success"]:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #388e3c, stop:1 #4caf50);
            }
            QPushButton[type="danger"] {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #c62828, stop:1 #e53935);
                color: white;
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 50px;
                padding: 8px 16px;
                font-weight: 600;
            }
            QPushButton[type="danger"]:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #d32f2f, stop:1 #ef5350);
            }
        """)

    def _apply_status_style(self, status: CameraStatus):
        border_colors = {
            CameraStatus.DISCONNECTED: "#404040",
            CameraStatus.CONNECTING: "#FF9800",
            CameraStatus.CONNECTED: "#4CAF50",
            CameraStatus.ERROR: "#f44336",
            CameraStatus.RECORDING: "#FF9800"
        }
        hover_bg = {
            CameraStatus.DISCONNECTED: "#e0e0e0",
            CameraStatus.CONNECTING: "#fff3e0",
            CameraStatus.CONNECTED: "#e8f5e9",
            CameraStatus.ERROR: "#ffebee",
            CameraStatus.RECORDING: "#fff3e0"
        }.get(status, "#e0e0e0")
        color = border_colors.get(status, "#404040")

        self.setStyleSheet(f"""
            CameraWidget {{
                background: #2d2d2d;
                border: 2px solid {color};
                border-radius: 20px;
            }}
            CameraWidget:hover {{
                background: {hover_bg};
                border-color: {color};
            }}
            QLabel#cameraName {{ color: #ffffff; font-weight: bold; font-size: 14px; }}
            QLabel#cameraInfo {{ color: rgba(255,255,255,0.5); font-size: 11px; }}
            QLabel#cameraFps {{ color: rgba(255,255,255,0.5); font-size: 11px; }}
            QLabel#cameraPause {{ color: #FF9800; font-size: 11px; font-weight: bold; }}
            QLabel#cameraStatus {{ font-size: 11px; }}
            CameraWidget:hover QLabel#cameraName {{ color: #1a1a2e; }}
            CameraWidget:hover QLabel#cameraInfo {{ color: rgba(0,0,0,0.6); }}
            CameraWidget:hover QLabel#cameraFps {{ color: rgba(0,0,0,0.6); }}
            CameraWidget:hover QLabel#cameraPause {{ color: #e65100; }}
            QPushButton {{
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 14px;
                padding: 0px;
            }}
            QPushButton:hover {{
                background: rgba(0,0,0,0.1);
                border-color: rgba(0,0,0,0.3);
            }}
            QPushButton[type="capture"] {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1565c0, stop:0.5 #4a148c, stop:1 #1565c0);
                color: white;
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 50px;
                padding: 8px 16px;
                font-weight: 600;
            }}
            QPushButton[type="capture"]:hover {{
                border-color: rgba(255,255,255,0.5);
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1e88e5, stop:0.5 #6a1b9a, stop:1 #1e88e5);
            }}
            QPushButton[type="success"] {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2e7d32, stop:1 #43a047);
                color: white;
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 50px;
                padding: 8px 16px;
                font-weight: 600;
            }}
            QPushButton[type="success"]:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #388e3c, stop:1 #4caf50);
            }}
            QPushButton[type="danger"] {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #c62828, stop:1 #e53935);
                color: white;
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 50px;
                padding: 8px 16px;
                font-weight: 600;
            }}
            QPushButton[type="danger"]:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #d32f2f, stop:1 #ef5350);
            }}
            QPushButton[type="paused"] {{
                background: rgba(255, 152, 0, 0.3);
                border-color: #FF9800;
            }}
        """)

    def _create_ip_buttons(self, header_layout):
        """
        FASE 6: Los botones de plugins se inyectan vía CameraWidgetExtension.

        El Core SOLO crea los botones esenciales (pausa, eliminar).
        Los plugins añaden sus botones (flash, audio, etc.) dinámicamente.
        """
        # Los botones base ya se añaden antes en _setup_ui
        # Aquí solo insertamos los plugins
        pass

    def _apply_extension_widgets(self, header_layout):
        """
        Consulta al ExtensionRegistry y añade widgets de plugins al header.

        Se llama durante _setup_ui() y también cuando un plugin se activa/desactiva.
        """
        try:
            from core.extension_registry import get_extension_registry
            from core.extensions.interfaces import CameraWidgetExtension

            registry = get_extension_registry()
            if registry is None:
                return

            extensions = registry.get(CameraWidgetExtension)
            if not extensions:
                return

            # Ordenar por prioridad
            extensions = sorted(
                extensions,
                key=lambda e: e.get_priority() if hasattr(e, 'get_priority') else 50,
            )

            for ext in extensions:
                try:
                    widgets = ext.get_widgets(self.camera.id, self)
                    if not widgets:
                        continue
                    for w in widgets:
                        if w is not None and w.parent() is None:
                            header_layout.addWidget(w)
                except Exception as e:
                    logger.error(
                        f"❌ CameraWidgetExtension falló: {e}",
                        exc_info=True,
                    )
        except Exception as e:
            logger.debug(f"⚠️ Error aplicando extensiones: {e}")

    def refresh_extension_widgets(self):
        """
        Re-aplica los widgets de extensión.

        Llamar cuando un plugin se activa/desactiva en runtime.
        """
        # Localizar el header_layout original
        # Es el primer QHBoxLayout del widget
        # (más simple: buscar el layout y limpiar widgets de extensiones)
        # Por simplicidad, recreamos el header
        # (en producción, guardar referencia al header_layout en __init__)
        pass

    # ==================== FLASH ====================

    def _toggle_flash(self):
        if self.camera.is_screen or self.camera.is_local:
            return
        self.flash_active = not self.flash_active
        if self.flash_active:
            self.flash_btn.setProperty("type", "flash-on")
            self.flash_btn.setToolTip("Flash encendido")
        else:
            self.flash_btn.setProperty("type", "")
            self.flash_btn.setToolTip("Flash apagado")
        self.flash_btn.style().unpolish(self.flash_btn)
        self.flash_btn.style().polish(self.flash_btn)
        logger.debug(
            f"🔦 [flash] {self.camera.name}: {'ON' if self.flash_active else 'OFF'}"
        )
        self.flash_toggled.emit(self.camera.id, self.flash_active)

    def _toggle_auto_flash(self, checked: bool):
        self.auto_flash_enabled = checked
        self.camera.auto_flash = checked
        logger.debug(
            f"⚡ [auto_flash] {self.camera.name}: {'ON' if checked else 'OFF'}"
        )
        self.auto_flash_toggled.emit(self.camera.id, checked)

    def is_auto_flash_enabled(self) -> bool:
        return (
            self.auto_flash_enabled
            and not self.camera.is_screen
            and not self.camera.is_local
        )

    def set_flash_state(self, enabled: bool):
        if self.camera.is_screen or self.camera.is_local:
            return
        self.flash_active = enabled
        if enabled:
            self.flash_btn.setProperty("type", "flash-on")
        else:
            self.flash_btn.setProperty("type", "")
        self.flash_btn.style().unpolish(self.flash_btn)
        self.flash_btn.style().polish(self.flash_btn)

    # ==================== EVENTOS ====================

    def _on_mouse_press(self, event: QMouseEvent):
        self.setFocus()

    def _on_double_click(self, event: QMouseEvent):
        if not self._animating:
            self.toggle_expand_requested.emit(self.camera.id)

    def set_selected(self, selected: bool):
        self._is_selected = selected
        if selected:
            self.selection_indicator.setText("✓")
            self._apply_selected_style()
        else:
            self.selection_indicator.setText("")
            self._apply_status_style(self.camera.status)
        self.selection_changed.emit(self.camera.id, selected)

    def _apply_selected_style(self):
        self.setStyleSheet("""
            CameraWidget {
                background: rgba(76, 175, 80, 0.15);
                border: 2px solid #4CAF50;
                border-radius: 20px;
            }
            CameraWidget:hover {
                background: #c8e6c9;
                border-color: #4CAF50;
            }
            CameraWidget QLabel { color: #ffffff; }
            CameraWidget:hover QLabel { color: #1a1a2e; }
            QPushButton {
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 14px;
                padding: 0px;
            }
            QPushButton:hover {
                background: rgba(0,0,0,0.1);
                border-color: rgba(0,0,0,0.3);
            }
        """)

    def _update_selection_style(self):
        if self._is_selected:
            self._apply_selected_style()
        else:
            self._apply_base_style()

    def _apply_video_overlays(self, force: bool = False):
        """
        Aplica los VideoOverlay registrados al video_frame.
        Solo se aplica cuando cambian o con force=True.
        """
        try:
            from core.extension_registry import get_extension_registry
            from core.extensions.interfaces import VideoOverlay

            registry = get_extension_registry()
            overlays = registry.get(VideoOverlay)

            if not overlays:
                return

            # ✅ Cache: si ya aplicamos los overlays, no repetir
            overlay_ids = tuple(id(o) for o in overlays)
            if not force and getattr(self, '_applied_overlay_ids', None) == overlay_ids:
                # Solo reposicionar si cambió el tamaño
                for widget in self.video_frame.findChildren(QWidget):
                    if hasattr(widget, '_is_video_overlay'):
                        self._position_overlay(widget)
                return

            # Ordenar por prioridad (mayor = más arriba)
            overlays = sorted(
                overlays,
                key=lambda o: o.get_priority() if hasattr(o, 'get_priority') else 50,
                reverse=True,
            )

            for overlay in overlays:
                try:
                    if not overlay.should_show(self.camera.id):
                        continue

                    widget = overlay.get_overlay_widget(self.camera.id)
                    if widget is None:
                        continue

                    # Reparentar al video_frame
                    if widget.parent() is not self.video_frame:
                        widget.setParent(self.video_frame)
                        widget.raise_()

                    widget._is_video_overlay = True
                    # Posicionar arriba-derecha
                    self._position_overlay(widget)
                except Exception as e:
                    logger.debug(f"Error aplicando VideoOverlay: {e}")
        except Exception:
            pass

    def _position_overlay(self, widget):
        """Posiciona un overlay en la esquina superior derecha."""
        try:
            frame_w = self.video_frame.width()
            widget.adjustSize()
            widget.move(
                max(4, frame_w - widget.width() - 4),
                4,
            )
        except Exception:
            pass

    # ==================== EXPANSIÓN ====================

    def toggle_expand(self, expanded: bool, target_geometry: QRect = None):
        if self._animating:
            self.expand_animation.stop()
            self._animating = False

        logger.debug(
            f"🔍 [expand] {self.camera.name}: expanded={expanded}, "
            f"target={target_geometry}"
        )

        self.is_expanded = expanded
        self._target_geometry = target_geometry
        current_geo = self.geometry()

        if expanded:
            self._original_geometry = current_geo
            self.setMinimumSize(640, 480)
            self.setMaximumSize(16777215, 16777215)

            if not target_geometry:
                parent_width = self.parent().width() if self.parent() else 800
                target_geometry = QRect(
                    current_geo.x(), current_geo.y(),
                    parent_width - 20, 600
                )
            if target_geometry.width() < 640:
                target_geometry.setWidth(640)
            if target_geometry.height() < 480:
                target_geometry.setHeight(480)

            self.expand_animation.setStartValue(current_geo)
            self.expand_animation.setEndValue(target_geometry)
            self._animating = True
            self.expand_animation.start()
        else:
            self.setMinimumSize(320, 280)
            self.setMaximumSize(480, 400)
            target_geo = self._original_geometry or QRect(
                current_geo.x(), current_geo.y(), 400, 350
            )
            self.expand_animation.setStartValue(current_geo)
            self.expand_animation.setEndValue(target_geo)
            self._animating = True
            self.expand_animation.start()

    def _on_animation_finished(self):
        self._animating = False
        if self.is_expanded:
            self.setMinimumSize(640, 480)
            self.setMaximumSize(16777215, 16777215)
        else:
            self.setMinimumSize(320, 280)
            self.setMaximumSize(480, 400)
        self.expand_finished.emit()
        if self._last_frame is not None:
            self.update_frame(self._last_frame)

    # ==================== PAUSA ====================

    def _toggle_pause(self):
        self.is_paused = not self.is_paused

        logger.debug(
            f"⏸️ [pause] {self.camera.name}: paused={self.is_paused}"
        )

        if self.is_paused:
            self._paused_frame = self._last_frame
            self.pause_btn.setText("▶")
            self.pause_btn.setProperty("type", "paused")
            self.pause_indicator.setText("⏸ PAUSADO")
            if self._paused_frame is not None:
                self.update_frame(self._paused_frame)
            if self._display_timer_running:
                self._tm.stop(f"{self._owner}.display")
                self._display_timer_running = False
        else:
            self.pause_btn.setText("⏸")
            self.pause_btn.setProperty("type", "")
            self.pause_indicator.setText("")
            self._paused_frame = None

        self.pause_btn.style().unpolish(self.pause_btn)
        self.pause_btn.style().polish(self.pause_btn)

    # ==================== FRAMES ====================

    def update_frame(self, qimage: QImage):
        """Actualiza con throttling - usa start/stop en lugar de create"""
        if self.is_paused:
            return

        if qimage is None or qimage.isNull():
            logger.debug(f"⚠️ [widget] {self.camera.name}: qimage nulo")
            return

        self._pending_frame = qimage
        self._last_frame = qimage
        self._fps_counter += 1

        # ✅ Activar timer solo si no está corriendo
        if not self._display_timer_running:
            self._tm.start(f"{self._owner}.display")
            self._display_timer_running = True
            self._empty_cycles = 0
            logger.debug(
                f"▶️ [widget] {self.camera.name}: display timer ARRANCADO"
            )

    def _process_pending_frame(self):
        """Procesa frame pendiente"""
        if self.is_paused:
            self._pending_frame = None
            return

        if self._pending_frame is None:
            self._empty_cycles += 1
            if self._empty_cycles > 30 and self._display_timer_running:
                self._tm.stop(f"{self._owner}.display")
                self._display_timer_running = False
                self._empty_cycles = 0
                logger.debug(
                    f"⏸️ [widget] {self.camera.name}: display timer DETENIDO "
                    f"(30 ciclos vacíos)"
                )
            return

        self._empty_cycles = 0

        try:
            qimage = self._pending_frame
            self._pending_frame = None

            label_width = self.video_label.width()
            label_height = self.video_label.height()

            if label_width < 10 or label_height < 10:
                logger.debug(
                    f"⚠️ [widget] {self.camera.name}: label muy pequeño "
                    f"({label_width}x{label_height}), frame descartado"
                )
                return

            target_size = QSize(label_width, label_height)

            scaled_pixmap = self._pixmap_pool.get_scaled(
                qimage,
                target_size,
                aspect_mode=Qt.KeepAspectRatio,
                transform_mode=Qt.FastTransformation
            )

            if scaled_pixmap is not None:
                self.video_label.setPixmap(scaled_pixmap)
                if self.video_label.styleSheet() != "background-color: #000000; border-radius: 12px;":
                    self.video_label.setStyleSheet(
                        "background-color: #000000; border-radius: 12px;"
                    )
                self._apply_video_overlays()
            else:
                logger.debug(
                    f"⚠️ [widget] {self.camera.name}: get_scaled devolvió None"
                )
        except Exception as e:
            logger.debug(f"Error procesando frame: {e}")

    def _update_fps(self):
        self.fps_label.setText(f"FPS: {self._fps_counter}")
        if not hasattr(self, '_fps_log_counter'):
            self._fps_log_counter = 0
        self._fps_log_counter += 1
        if self._fps_log_counter % 30 == 0:
            pending = 1 if self._pending_frame is not None else 0
            logger.debug(
                f"📊 [widget] {self.camera.name}: FPS={self._fps_counter}, "
                f"pending={pending}, timer_running={self._display_timer_running}, "
                f"empty_cycles={self._empty_cycles}"
            )
        self._fps_counter = 0

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_pixmap_pool'):
            self._pixmap_pool.invalidate()
        if self._last_frame is not None and not self.is_paused:
            self.update_frame(self._last_frame)
        elif self.is_paused and self._paused_frame is not None:
            self.update_frame(self._paused_frame)

        self._apply_video_overlays()

    def _apply_config_update(self, cfg: dict):
        """Aplica cambios de config al widget SIN reiniciar"""
        logger.debug(
            f"🔧 [config] {self.camera.name}: aplicando nueva config "
            f"(min={cfg.get('camera_widget_min_width')}x"
            f"{cfg.get('camera_widget_min_height')}, "
            f"anim={cfg.get('anim_duration_ms')}ms)"
        )

        self.setMinimumSize(
            cfg.get("camera_widget_min_width", 320),
            cfg.get("camera_widget_min_height", 280)
        )
        self.setMaximumSize(
            cfg.get("camera_widget_max_width", 480),
            cfg.get("camera_widget_max_height", 400)
        )

        if hasattr(self, 'expand_animation'):
            self.expand_animation.setDuration(cfg.get("anim_duration_ms", 350))

        logger.debug(f"  🔧 Config actualizada en widget {self.camera.name}")

    # ==================== STATUS ====================

    def set_status(self, status: CameraStatus):
        logger.debug(
            f"🔄 [widget] {self.camera.name}: status {self.camera.status} → {status}"
        )

        self._apply_status_style(status)

        status_texts = {
            CameraStatus.DISCONNECTED: "● Desconectado",
            CameraStatus.CONNECTING: "● Conectando...",
            CameraStatus.CONNECTED: "● Conectado",
            CameraStatus.ERROR: "● Error",
            CameraStatus.RECORDING: "● Grabando"
        }
        status_colors = {
            CameraStatus.DISCONNECTED: "#888",
            CameraStatus.CONNECTING: "#FF9800",
            CameraStatus.CONNECTED: "#4CAF50",
            CameraStatus.ERROR: "#f44336",
            CameraStatus.RECORDING: "#FF9800"
        }
        self.status_label.setText(status_texts.get(status, "● Desconocido"))
        color = status_colors.get(status, "#888")
        self.status_label.setStyleSheet(f"QLabel {{ color: {color}; font-size: 11px; }}")

    # ==================== GRABACIÓN ====================

    def _toggle_recording(self):
        """Alterna la grabación. Si no hay audio activo, pregunta antes de grabar."""
        from audio.audio_manager import audio_manager

        # ✅ NUEVO: Si va a EMPEZAR a grabar y no hay audio activo, preguntar
        if not self.is_recording:
            supports_audio = not self.camera.is_screen and not self.camera.is_local
            if supports_audio:
                audio_active = audio_manager.is_camera_audio_active(self.camera.id)
                if not audio_active:
                    logger.debug(
                        f"🎬 [widget] {self.camera.name}: grabación sin audio, "
                        f"preguntando al usuario"
                    )
                    reply = QMessageBox.question(
                        self,
                        "Grabar con audio",
                        f"¿Deseas activar el audio para esta grabación de "
                        f"'{self.camera.name}'?\n\n"
                        f"Si eliges 'Sí', se activará el audio y se escuchará "
                        f"mientras grabas.\n"
                        f"Si eliges 'No', la grabación será silenciosa.",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.Yes
                    )

                    if reply == QMessageBox.Yes:
                        logger.info(
                            f"🎤 [widget] Usuario activó audio para grabación"
                        )
                        if not self.audio_btn.isChecked():
                            self.audio_btn.setChecked(True)
                            self._toggle_audio(True)
                    else:
                        logger.info(
                            f"🔇 [widget] Usuario eligió grabar sin audio"
                        )

        self.is_recording = not self.is_recording

        logger.debug(
            f"🎬 [widget] {self.camera.name}: grabación "
            f"{'INICIADA' if self.is_recording else 'DETENIDA'}"
        )

        if self.is_recording:
            self.record_btn.setText("⏹ Detener")
            self.record_btn.setProperty("type", "danger")
            self.recording_time = 0
            if self._tm.exists(f"{self._owner}.recording") and not self._tm.is_running(f"{self._owner}.recording"):
                self._tm.start(f"{self._owner}.recording", 1000)
            self._tm.create(
                f"{self._owner}.recording",
                1000,
                self._update_recording_indicator,
                start=True
            )
        else:
            self.record_btn.setText("🎬 Grabar")
            self.record_btn.setProperty("type", "success")
            self._tm.stop(f"{self._owner}.recording")

        self.record_btn.style().unpolish(self.record_btn)
        self.record_btn.style().polish(self.record_btn)
        self.recording_toggled.emit(self.camera.id, self.is_recording)

    def _update_recording_indicator(self):
        self.recording_time += 1
        minutes = self.recording_time // 60
        seconds = self.recording_time % 60
        self.status_label.setText(f"● Grabando {minutes:02d}:{seconds:02d}")

    def show_error(self, error_message: str):
        logger.debug(
            f"❌ [widget] {self.camera.name}: {error_message}"
        )
        self.video_label.setText(f"⚠️\n{error_message}")
        self.video_label.setStyleSheet(
            "color: #f44336; font-size: 12px; "
            "background-color: #000000; border-radius: 12px;"
        )
        self.set_status(CameraStatus.ERROR)

    # ==================== CLEANUP ====================

    def cleanup(self):
        """Limpia recursos al eliminar el widget"""
        logger.debug(f"🧹 [cleanup] INICIO: {self.camera.name}")
        logger.debug(
            f"🧹 [cleanup] Timers activos del owner '{self._owner}': "
            f"{[n for n in self._tm.list_timers() if n.startswith(self._owner)]}"
        )

        try:
            from audio.audio_manager import audio_manager
            audio_manager.stop_camera_audio(self.camera.id)
        except Exception:
            pass

        self._tm.stop_group(self._owner)
        logger.debug(
            f"🧹 [cleanup] Timers tras stop_group: "
            f"{[n for n in self._tm.list_timers() if n.startswith(self._owner)]}"
        )
        self._display_timer_running = False
        self._empty_cycles = 0

        try:
            if self.expand_animation.state() == QPropertyAnimation.Running:
                self.expand_animation.stop()
        except Exception:
            pass

        if hasattr(self, '_pixmap_pool'):
            self._pixmap_pool.clear()
            
        logger.debug(f"🧹 [cleanup] FIN: {self.camera.name}")