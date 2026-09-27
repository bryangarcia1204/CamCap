"""
Ventana principal de ProCamera - v6
- FASE 3: FrameAnalyzers vía ExtensionRegistry
- Monitor de sistema
- Audio local
- Cierre ordenado
- Propagación en caliente
"""
import os
import cv2
import numpy as np
import requests
import time
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict

from PySide6.QtWidgets import (QMainWindow, QWidget, QDialog,
                               QHBoxLayout, QToolBar, QStatusBar,
                               QMessageBox, QSplitter, QPushButton,
                               QLabel, QMenu, QSizePolicy, QDockWidget)
from PySide6.QtCore import Qt, Signal, QObject, QRunnable, QThreadPool
from PySide6.QtGui import QAction, QKeySequence

from core.models import CameraDevice, CameraStatus
from core.settings_manager import settings_manager
from core.engine.camera_engine import CameraManager
from ui.video_preview import VideoPreview
from core.file_manager import FileManager
from ui.camera_grid import CameraGrid
from ui.file_explorer import FileExplorer
from ui.settings_dialog import SettingsDialog
from ui.image_preview import ImagePreview
from ui.loading_manager import LoadingManager, LoadingContext
from ui.system_monitor_widget import SystemMonitorWidget
from utils.logger import get_logger
from utils.system_monitor import system_monitor
from utils.timer_manager import timer_manager
from utils.config_loader import advanced_config

logger = get_logger("MainWindow")


class MotionProcessor(QRunnable):
    """Worker para procesar la detección de movimiento en hilo separado."""

    class Signals(QObject):
        finished = Signal()
        error = Signal(str)

    def __init__(self, camera_name, frame, rects, analyzer, settings, callback):
        super().__init__()
        self.camera_name = camera_name
        self.frame = frame
        self.rects = rects
        self.analyzer = analyzer  # MotionAnalyzer o None
        self.settings = settings
        self.callback = callback
        self.signals = self.Signals()

    def run(self):
        try:
            image_path = None
            if self.frame is not None:
                directory = "detected/motion_detector"
                os.makedirs(directory, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_camera_name = "".join(
                    c for c in self.camera_name
                    if c.isalnum() or c in (' ', '_', '-')
                ).rstrip()
                filename = f"motion_{timestamp}_{safe_camera_name}.jpg"
                image_path = os.path.join(directory, filename)

                if self.analyzer is not None and hasattr(self.analyzer, 'draw_motion_rects'):
                    # Necesitamos el camera_id — lo pasamos como 0 si no lo tenemos
                    frame_with_rects = self.frame
                    # Intentar dibujar con el analyzer si lo soporta
                    try:
                        frame_with_rects = self.analyzer.draw_motion_rects(
                            self.settings.camera_id if hasattr(self.settings, 'camera_id') else 0,
                            self.frame, self.rects
                        )
                    except Exception:
                        frame_with_rects = self.frame
                else:
                    frame_with_rects = self.frame

                success, buffer = cv2.imencode(
                    '.jpg', frame_with_rects,
                    [cv2.IMWRITE_JPEG_QUALITY, 85]
                )
                if success:
                    with open(image_path, 'wb') as f:
                        f.write(buffer.tobytes())
                    logger.info(f"📸 Captura movimiento: {image_path}")

            if self.callback:
                self.callback(image_path)
        except Exception as e:
            logger.error(f"Error en MotionProcessor: {e}", exc_info=True)
            self.signals.error.emit(str(e))
        finally:
            self.signals.finished.emit()


class MainWindow(QMainWindow):
    """Ventana principal."""

    camera_removal_finished = Signal(int)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ProCamera - Estación de Control")
        self.setMinimumSize(1200, 800)

        self.camera_removal_finished.connect(self._finish_camera_removal)
        self.thread_pool = QThreadPool.globalInstance()

        # Componentes
        self.settings = settings_manager
        self.camera_manager = CameraManager()
        self.capture_settings = self.settings.get_capture_settings()
        self.file_manager = FileManager(self.capture_settings)
        self.loading_overlay = LoadingManager.init_overlay(self)
        self._tm = timer_manager

        # Estado
        self.is_recording_all = False
        self.auto_capture_interval = 0
        self.camera_threads: Dict = {}
        self._is_closing = False
        self.change_counter_camera = settings_manager._settings.value("cameras/count")

        advanced_config.load()
        self._setup_ui()
        self._load_ui_state()

        system_monitor.start()
        logger.info("📊 SystemMonitor iniciado")

        loading_timeout = advanced_config.get("loading_timeout", 500)
        self._schedule_once(loading_timeout, self._load_cameras_deferred)
        self._schedule_once(loading_timeout + 100, self._apply_ui_extensions)
        self._schedule_once(2000, self.timers_list)

    # ==================== INICIALIZACIÓN ====================

    def timers_list(self):
        timers = self._tm.list_timers()
        logger.debug("Timers activos:")
        for t in timers:
            logger.debug(f" - {t} {'Activo' if self._tm.is_running(t) else 'Detenido'}")

    def _setup_ui(self):
        self._create_menu_bar()
        self._create_toolbar()

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)

        self.file_explorer = FileExplorer()
        self.file_explorer.file_selected.connect(self._on_file_selected)
        splitter.addWidget(self.file_explorer)

        self.camera_grid = CameraGrid()
        self.camera_grid.capture_requested.connect(self._on_capture_single)
        self.camera_grid.capture_all_requested.connect(self._on_capture_all)
        self.camera_grid.recording_toggled.connect(self._on_recording_toggle)
        self.camera_grid.camera_removed.connect(self._on_camera_removed)
        self.camera_grid.add_camera_requested.connect(self._show_settings)
        splitter.addWidget(self.camera_grid)

        splitter.setSizes([300, 900])
        main_layout.addWidget(splitter)

        self.image_preview = ImagePreview()
        self.image_preview.close_btn.clicked.connect(self.image_preview.hide)
        self.image_preview.hide()

        self.video_preview = VideoPreview()
        self.video_preview.closed.connect(self._on_video_preview_closed)
        self.video_preview.hide()

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel("Listo")
        self.status_bar.addWidget(self.status_label)
        self.cameras_count = QLabel("0 cámaras")
        self.status_bar.addPermanentWidget(self.cameras_count)

        self._debug_console_dock = QDockWidget("🖥️ Consola de Debug", self)
        self._debug_console_dock.setAllowedAreas(Qt.BottomDockWidgetArea)
        self._debug_console_dock.setFeatures(
            QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable
        )
        self._debug_console_dock.setVisible(False)
        self._debug_console_placeholder = QWidget()
        self._debug_console_dock.setWidget(self._debug_console_placeholder)
        self.addDockWidget(Qt.BottomDockWidgetArea, self._debug_console_dock)
        self._debug_console_dock.hide()

    def _create_menu_bar(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&Archivo")
        new_action = QAction("&Nuevo Proyecto", self)
        new_action.setShortcut(QKeySequence("Ctrl+N"))
        new_action.triggered.connect(self._new_project)
        file_menu.addAction(new_action)
        file_menu.addSeparator()
        exit_action = QAction("&Salir", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        camera_menu = menubar.addMenu("&Cámara")
        add_cam_action = QAction("&Agregar Cámara", self)
        add_cam_action.setShortcut(QKeySequence("Ctrl+Shift+A"))
        add_cam_action.triggered.connect(self._show_settings)
        camera_menu.addAction(add_cam_action)
        camera_menu.addSeparator()
        capture_all_action = QAction("&Capturar Todas", self)
        capture_all_action.setShortcut(QKeySequence("Ctrl+Shift+C"))
        capture_all_action.triggered.connect(self._on_capture_all)
        camera_menu.addAction(capture_all_action)

        view_menu = menubar.addMenu("&Ver")
        refresh_action = QAction("&Refrescar", self)
        refresh_action.setShortcut(QKeySequence("F5"))
        refresh_action.triggered.connect(self._refresh_view)
        view_menu.addAction(refresh_action)
        view_menu.addSeparator()
        toggle_explorer = QAction("&Explorador de Archivos", self)
        toggle_explorer.setCheckable(True)
        toggle_explorer.setChecked(True)
        toggle_explorer.triggered.connect(self._toggle_file_explorer)
        view_menu.addAction(toggle_explorer)

        settings_menu = menubar.addMenu("&Configuración")
        settings_action = QAction("&Preferencias", self)
        settings_action.setShortcut(QKeySequence("Ctrl+,"))
        settings_action.triggered.connect(self._show_settings)
        settings_menu.addAction(settings_action)
        settings_menu.addSeparator()
        clear_data_action = QAction("&Limpiar Datos", self)
        clear_data_action.triggered.connect(self._clear_all_data)
        settings_menu.addAction(clear_data_action)

    def _apply_ui_extensions(self):
        """Aplica TODAS las UIExtension (toolbar, menu, status bar, dock)."""
        logger.info("🎨 Aplicando extensiones de UI...")
        try:
            from core.extension_registry import get_extension_registry
            from core.extensions.interfaces import UIExtension
            registry = get_extension_registry()
        except Exception as e:
            logger.debug(f"⚠️ Registry no disponible: {e}")
            return

        # Toolbar (slots "left" y "right")
        toolbar = getattr(self, "main_toolbar", None)
        if toolbar is not None:
            self._apply_toolbar_extensions(toolbar)

        # Status bar
        try:
            from core.extensions.interfaces import StatusWidget
            providers = registry.get(StatusWidget)
            for provider in providers:
                try:
                    widget = provider.get_widget()
                    if widget and self.status_bar:
                        self.status_bar.addPermanentWidget(widget)
                except Exception as e:
                    logger.error(f"❌ StatusWidget falló: {e}")
        except Exception:
            pass

        logger.info("✅ Extensiones de UI aplicadas")

    def _apply_toolbar_extensions(self, toolbar):
        """Inyecta botones de plugins en la toolbar (slots left/right)."""
        try:
            from core.extension_registry import get_extension_registry
            from core.extensions.interfaces import UIExtension

            registry = get_extension_registry()
            if registry is None:
                return

            # Botones "left" (antes del spacer)
            left_exts = [
                ext for ext in registry.get(UIExtension)
                if ext.get_target() == "main_toolbar" and ext.get_slot() == "left"
            ]
            left_exts = sorted(
                left_exts,
                key=lambda e: e.get_priority() if hasattr(e, "get_priority") else 50,
            )

            for ext in left_exts:
                try:
                    widgets = ext.get_widgets({"main_window": self}) or []
                    for w in widgets:
                        if w is None:
                            continue
                        if w.parent() is None:
                            toolbar.addWidget(w)
                        w.setProperty("_is_plugin_widget", True)
                    if widgets:
                        toolbar.addSeparator()
                except Exception as e:
                    logger.error(
                        f"❌ UIExtension toolbar '{ext.get_id()}' falló: {e}",
                        exc_info=True,
                    )

            # Botones "right" (al final)
            right_exts = [
                ext for ext in registry.get(UIExtension)
                if ext.get_target() == "main_toolbar" and ext.get_slot() == "right"
            ]
            right_exts = sorted(
                right_exts,
                key=lambda e: e.get_priority() if hasattr(e, "get_priority") else 50,
            )
            for ext in right_exts:
                try:
                    widgets = ext.get_widgets({"main_window": self}) or []
                    for w in widgets:
                        if w is None:
                            continue
                        if w.parent() is None:
                            toolbar.addWidget(w)
                        w.setProperty("_is_plugin_widget", True)
                except Exception as e:
                    logger.error(
                        f"❌ UIExtension toolbar '{ext.get_id()}' falló: {e}",
                        exc_info=True,
                    )
        except Exception as e:
            logger.debug(f"⚠️ Error aplicando toolbar: {e}")

    def _create_toolbar(self):
        toolbar = QToolBar("Principal")
        toolbar.setObjectName("MainToolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self.main_toolbar = toolbar

        # === Botones Core ===
        capture_all_btn = QPushButton("📸 Capturar Todas")
        capture_all_btn.clicked.connect(self._on_capture_all)
        capture_all_btn.setStyleSheet(self._get_toolbar_btn_style("#2d7d9a", "#4da0c4"))
        toolbar.addWidget(capture_all_btn)
        toolbar.addSeparator()

        self.record_all_btn = QPushButton("🎬 Grabar Todas")
        self.record_all_btn.clicked.connect(self._on_record_all)
        self.record_all_btn.setStyleSheet(
            self._get_toolbar_btn_style("#4CAF50", "#388E3C")
        )
        toolbar.addWidget(self.record_all_btn)
        toolbar.addSeparator()

        # ✅ Slot "left" — plugins inyectan aquí (ej. audio: 🎤 Mic PC)
        self._apply_toolbar_slot(toolbar, "left")

        settings_btn = QPushButton("⚙️ Configurar")
        settings_btn.clicked.connect(self._show_settings)
        toolbar.addWidget(settings_btn)
        toolbar.addSeparator()

        toolbar.addWidget(QLabel("Calidad:"))
        self.quality_combo = QPushButton("Alta")
        self.quality_combo.setMenu(self._create_quality_menu())
        toolbar.addWidget(self.quality_combo)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)

        self.auto_capture_btn = QPushButton("🔄 Auto")
        self.auto_capture_btn.setCheckable(True)
        self.auto_capture_btn.clicked.connect(self._toggle_auto_capture)
        toolbar.addWidget(self.auto_capture_btn)

        toolbar.addSeparator()
        monitor_label = QLabel("📊")
        monitor_label.setStyleSheet("padding: 0 4px; font-size: 14px;")
        toolbar.addWidget(monitor_label)

        self.system_monitor_widget = SystemMonitorWidget()
        toolbar.addWidget(self.system_monitor_widget)

        # ✅ Slot "right" — plugins inyectan al final
        self._apply_toolbar_slot(toolbar, "right")

    def _apply_toolbar_slot(self, toolbar, slot: str):
        """Inyecta UIExtension en un slot específico de la toolbar."""
        try:
            from core.extension_registry import get_extension_registry
            from core.extensions.interfaces import UIExtension
            registry = get_extension_registry()
            if registry is None:
                return
            exts = [
                e for e in registry.get(UIExtension)
                if e.get_target() == "main_toolbar" and e.get_slot() == slot
            ]
            exts = sorted(
                exts,
                key=lambda e: e.get_priority() if hasattr(e, "get_priority") else 50,
            )
            for ext in exts:
                try:
                    for w in ext.get_widgets({"main_window": self}) or []:
                        if w is not None and w.parent() is None:
                            toolbar.addWidget(w)
                            w.setProperty("_is_plugin_widget", True)
                except Exception as e:
                    logger.error(f"❌ UIExtension '{ext.get_id()}' falló: {e}")
        except Exception as e:
            logger.debug(f"⚠️ Error aplicando toolbar slot {slot}: {e}")

    def _get_toolbar_btn_style(self, bg, hover):
        return f"""
            QPushButton {{
                background-color: {bg};
                border: none;
                padding: 6px 16px;
                border-radius: 4px;
                font-weight: bold;
                color: white;
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
        """

    def _create_quality_menu(self) -> QMenu:
        menu = QMenu()
        for name, value in {"Alta": 95, "Media": 85, "Baja": 70}.items():
            action = QAction(name, menu)
            action.triggered.connect(lambda checked, v=value: self._set_quality(v))
            menu.addAction(action)
        return menu

    # ==================== CARGA DE CÁMARAS ====================

    def _load_cameras_deferred(self):
        cameras = self.settings.get_cameras()
        if not cameras:
            self.status_label.setText("No hay cámaras configuradas")
            return
        LoadingManager.show_loading(
            "Conectando cámaras...",
            f"Cargando {len(cameras)} dispositivo(s)"
        )
        self._cameras_to_load = list(cameras)
        self._cameras_loaded_index = 0
        self._load_next_camera()

    def _load_next_camera(self):
        if self._cameras_loaded_index >= len(self._cameras_to_load):
            LoadingManager.hide_loading()
            self._update_status()
            return

        camera = self._cameras_to_load[self._cameras_loaded_index]
        self._cameras_loaded_index += 1

        total = len(self._cameras_to_load)
        progress = int((self._cameras_loaded_index / total) * 100)
        LoadingManager.update_loading(progress, f"Conectando {camera.name}...")

        if self.camera_manager.is_camera_closing(camera.id):
            logger.info(f"⏳ Cámara {camera.id} cerrándose, saltando...")
        elif camera.id in self.camera_grid.cameras:
            logger.debug(f"Cámara {camera.id} ya cargada")
        else:
            self._add_camera(camera)

        self._schedule_once(30, self._load_next_camera)

    def _add_camera(self, camera: CameraDevice):
        logger.info(f"📷 Añadiendo: {camera.name} (ID: {camera.id})")

        if self.camera_manager.is_camera_closing(camera.id):
            self._schedule_once(500, lambda: self._add_camera(camera))
            return

        if camera.id in self.camera_grid.cameras:
            return

        widget = self.camera_grid.add_camera_widget(camera)

        try:
            widget.flash_toggled.connect(self._on_flash_toggle)
            widget.auto_flash_toggled.connect(self._on_auto_flash_toggled)
        except Exception:
            pass

        if self.camera_manager.add_camera(camera):
            thread = self.camera_manager.get_thread(camera.id)
            if thread:
                thread.frame_ready.connect(widget.update_frame)
                thread.status_changed.connect(widget.set_status)
                thread.error_occurred.connect(widget.show_error)

                if hasattr(thread, 'motion_detected'):
                    try:
                        thread.motion_detected.connect(self._on_motion_detected)
                    except Exception:
                        pass
                if hasattr(thread, 'face_detected'):
                    try:
                        thread.face_detected.connect(self._on_face_detected)
                    except Exception:
                        pass
                if hasattr(thread, 'document_detected'):
                    try:
                        thread.document_detected.connect(self._on_document_detected)
                    except Exception:
                        pass
                if hasattr(thread, 'text_recognized'):
                    try:
                        thread.text_recognized.connect(self._on_text_recognized)
                    except Exception:
                        pass

                self._configure_camera_detections(camera, thread)
                self.camera_threads[camera.id] = thread
                logger.info(f"  ✅ Thread conectado")
        else:
            logger.error(f"  ❌ camera_manager.add_camera() falló")

        self.camera_grid._rearrange_grid()
        self._update_status()

    def _configure_camera_detections(self, camera: CameraDevice, thread):
        """
        FASE 3: los analyzers se cargan lazy desde el engine.
        El Core NO configura detectores legacy.
        Solo se configura escaneo legacy si el plugin document_scanner
        no está activo (fallback).

        Los flags motion_enabled/face_enabled viven en QSettings y los
        leen los analyzers directamente desde settings_manager.
        """
        try:
            # Verificar si hay analyzers disponibles
            from core.extension_registry import get_extension_registry
            from core.extensions.interfaces import FrameAnalyzer
            registry = get_extension_registry()
            has_analyzers = (
                registry is not None
                and len(registry.get(FrameAnalyzer)) > 0
            )

            if has_analyzers:
                logger.debug(
                    f"🎯 {camera.name}: usando FrameAnalyzers del registry"
                )
                # Forzar recarga de analyzers en el thread
                if hasattr(thread, "refresh_analyzers"):
                    thread.refresh_analyzers()
                return

            # Fallback legacy (solo si NO hay plugins de detección activos)
            logger.debug(f"ℹ️ {camera.name}: sin analyzers, activando legacy")
            det_settings = self.settings.get_detection_settings()
            if det_settings.get("motion_enabled") or det_settings.get("face_enabled"):
                if hasattr(thread, "setup_detection"):
                    thread.setup_detection(
                        motion_enabled=det_settings.get("motion_enabled", False),
                        face_enabled=det_settings.get("face_enabled", False),
                        motion_sensitivity=det_settings.get("motion_sensitivity", 25),
                        motion_min_area=det_settings.get("motion_min_area", 500),
                        face_tolerance=det_settings.get("face_tolerance", 0.6),
                    )
        except Exception as e:
            logger.error(f"Error configurando detecciones: {e}", exc_info=True)

    def _rebuild_toolbar_extensions(self):
        """Limpia y re-aplica los botones de plugins en la toolbar."""
        toolbar = self.main_toolbar
        if toolbar is None:
            return

        # Quitar botones de plugin previos
        for action in list(toolbar.actions()):
            w = toolbar.widgetForAction(action)
            if w is not None and w.property("_is_plugin_widget"):
                toolbar.removeAction(action)
                w.setParent(None)
                w.deleteLater()

        # Re-aplicar
        self._apply_toolbar_slot(toolbar, "left")
        self._apply_toolbar_slot(toolbar, "right")

    # ==================== DETECCIONES ====================

    def _on_motion_detected(self, camera_id: int, rects: list):
        camera = self.camera_manager.get_camera(camera_id)
        if not camera:
            return
        thread = self.camera_manager.get_thread(camera_id)
        if not thread:
            return

        # FASE 3: el analyzer ya aplicó cooldown. No volver a chequear.
        # Compatibilidad con modo legacy: chequear cooldown si existe detector.
        motion_detector = getattr(thread, 'motion_detector', None)
        if motion_detector is not None:
            if hasattr(motion_detector, 'can_notify'):
                # Legacy ya notificó por can_notify en detect()
                pass

        det_settings = self.settings.get_detection_settings()
        if det_settings.get("auto_flash_on_motion", False):
            self._auto_flash_on_motion(camera_id)

        if det_settings.get("auto_record_on_motion", False):
            timeout = det_settings.get("auto_record_timeout", 2)
            self._show_auto_record_dialog(camera_id, timeout)
            return

        frame = thread.capture_frame()
        if frame is None:
            return

        settings = self.settings.get_capture_settings()

        # FASE 3: obtener analyzer para dibujar rects
        analyzer = None
        try:
            from core.extension_registry import get_extension_registry
            from core.extensions.interfaces import FrameAnalyzer
            registry = get_extension_registry()
            for a in registry.get(FrameAnalyzer):
                if hasattr(a, 'draw_motion_rects'):
                    analyzer = a
                    break
        except Exception:
            pass

        def on_motion_processed(image_path):
            if image_path:
                self.status_label.setText(
                    f"🚨 Movimiento en {camera.name} - Captura guardada"
                )
            else:
                self.status_label.setText(f"🚨 Movimiento en {camera.name}")

            try:
                from notifications.notification_manager import notification_manager
                notification_manager.notify_motion(camera.name, image_path)
            except Exception as e:
                logger.warning(f"No se pudo notificar: {e}")

        worker = MotionProcessor(
            camera_name=camera.name,
            frame=frame,
            rects=rects,
            analyzer=analyzer,
            settings=settings,
            callback=on_motion_processed
        )
        self.thread_pool.start(worker)
        self.status_label.setText(f"🚨 Movimiento detectado en {camera.name}...")

    def _auto_flash_on_motion(self, camera_id: int):
        thread = self.camera_manager.get_thread(camera_id)
        if not thread or not hasattr(thread, "toggle_flash"):
            return
        thread.toggle_flash(True)
        widget = self.camera_grid.get_camera_widget(camera_id)
        if widget and hasattr(widget, "_plugin_flash"):
            try:
                widget._plugin_flash["set_flash_state"](True)
            except Exception:
                pass
        flash_on_ms = advanced_config.get("flash_on_duration_ms", 2000)
        self._schedule_once(
            flash_on_ms + 1000,
            lambda: self._auto_flash_off(camera_id),
        )

    def _auto_flash_off(self, camera_id: int):
        thread = self.camera_manager.get_thread(camera_id)
        if thread and hasattr(thread, "toggle_flash"):
            thread.toggle_flash(False)
        widget = self.camera_grid.get_camera_widget(camera_id)
        if widget and hasattr(widget, "_plugin_flash"):
            try:
                widget._plugin_flash["set_flash_state"](False)
            except Exception:
                pass

    def _show_auto_record_dialog(self, camera_id: int, timeout: int):
        try:
            from ui.auto_record_dialog import AutoRecordDialog
            camera = self.camera_manager.get_camera(camera_id)
            if not camera:
                return
            dialog = AutoRecordDialog(camera.name, timeout, self)
            dialog.user_confirmed.connect(
                lambda: self._start_auto_recording(camera_id)
            )
            dialog.exec()
        except ImportError:
            self._start_auto_recording(camera_id)

    def _start_auto_recording(self, camera_id: int):
        thread = self.camera_manager.get_thread(camera_id)
        if thread and hasattr(thread, 'toggle_flash'):
            thread.toggle_flash(True)
        widget = self.camera_grid.get_camera_widget(camera_id)
        if widget and not widget.is_recording:
            widget.record_btn.click()
        self.status_label.setText("🎬 Grabando automáticamente...")

    def _on_face_detected(self, camera_id: int, locations: list, names: list):
        camera = self.camera_manager.get_camera(camera_id)
        if not camera:
            return
        thread = self.camera_manager.get_thread(camera_id)
        if not thread:
            return

        unknown_count = names.count("Desconocido")
        known_names = [n for n in names if n != "Desconocido"]

        if unknown_count > 0:
            frame = thread.capture_frame()
            if frame is None:
                return

            # FASE 3: obtener recognizer del analyzer o legacy
            recognizer = self._get_face_recognizer_for_camera(camera_id, thread)
            if recognizer is None:
                return

            try:
                directory = "detected/face_recognizer"
                os.makedirs(directory, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"intruder_{timestamp}_{camera.name}.jpg"
                image_path = os.path.join(directory, filename)

                frame_with_faces = recognizer.draw_faces(frame)
                success, buffer = cv2.imencode(
                    '.jpg', frame_with_faces,
                    [cv2.IMWRITE_JPEG_QUALITY, 90]
                )
                if success:
                    with open(image_path, 'wb') as f:
                        f.write(buffer.tobytes())
                    logger.info(f"📸 Captura intruso: {image_path}")

                    if advanced_config.get("face_auto_register_unknown", True):
                        self._register_unknown_face(
                            recognizer, frame, locations, names, camera.name
                        )

                try:
                    from notifications.notification_manager import notification_manager
                    notification_manager.notify_face_unknown(camera.name, image_path)
                except Exception:
                    pass

                self.status_label.setText(f"👤 Desconocido en {camera.name}")
            except Exception as e:
                logger.error(f"Error guardando captura: {e}")

        elif known_names:
            try:
                from notifications.notification_manager import notification_manager
                for name in known_names:
                    notification_manager.notify_face_known(camera.name, name)
            except Exception:
                pass

    def _get_face_recognizer_for_camera(self, camera_id: int, thread):
        """Obtiene el FaceRecognizer (del analyzer o legacy)."""
        # Intentar del analyzer
        try:
            from core.extension_registry import get_extension_registry
            from core.extensions.interfaces import FrameAnalyzer
            registry = get_extension_registry()
            for a in registry.get(FrameAnalyzer):
                if hasattr(a, '_recognizers') and camera_id in a._recognizers:
                    return a._recognizers[camera_id]
        except Exception:
            pass
        # Fallback legacy
        return getattr(thread, 'face_recognizer', None)

    def _register_unknown_face(self, recognizer, frame, locations, names, camera_name):
        try:
            min_face_size = advanced_config.get("face_min_face_size", 20)
            for i, name in enumerate(names):
                if name == "Desconocido" and i < len(locations):
                    top, right, bottom, left = locations[i]
                    h, w = frame.shape[:2]
                    top = max(0, min(top, h - 1))
                    right = max(0, min(right, w - 1))
                    bottom = max(0, min(bottom, h - 1))
                    left = max(0, min(left, w - 1))
                    if right <= left or bottom <= top:
                        continue
                    face_img = frame[top:bottom, left:right]
                    if (face_img.size == 0 or
                            face_img.shape[0] < min_face_size or
                            face_img.shape[1] < min_face_size):
                        continue

                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    safe_camera = "".join(
                        c for c in camera_name if c.isalnum() or c in ('_', '-')
                    ).strip() or "cam"
                    person_name = f"Desconocido_{safe_camera}_{timestamp}"
                    known_dir = "known_faces"
                    os.makedirs(known_dir, exist_ok=True)
                    save_path = os.path.join(known_dir, f"{person_name}.jpg")

                    cv2.imwrite(save_path, face_img)
                    logger.info(f"🆕 Rostro desconocido registrado: {save_path}")

                    try:
                        recognizer.load_known_faces()
                    except Exception as e:
                        logger.warning(f"No se pudo recargar caras: {e}")
                    break
        except Exception as e:
            logger.error(f"Error en auto-registro: {e}", exc_info=True)

    def _on_document_detected(self, camera_id: int, result: dict):
        camera = self.camera_manager.get_camera(camera_id)
        if camera:
            self.status_label.setText(
                f"📄 Documento en {camera.name} "
                f"(confianza: {result.get('confidence', 0):.0%})"
            )

    def _on_text_recognized(self, camera_id: int, text: str):
        camera = self.camera_manager.get_camera(camera_id)
        if camera and text.strip():
            preview = text.strip()[:50] + "..." if len(text) > 50 else text.strip()
            self.status_label.setText(f"📝 {camera.name}: {preview}")

    # ==================== CAPTURA ====================

    def _on_capture_single(self, camera_id: int):
        thread = self.camera_manager.get_thread(camera_id)
        if not thread:
            QMessageBox.warning(self, "Error", "No se encontró el hilo")
            return
        camera = self.camera_manager.get_camera(camera_id)
        if camera and camera.status != CameraStatus.CONNECTED:
            QMessageBox.warning(self, "Error", f"{camera.name} no conectada")
            return

        # ✅ Auto-flash: consultar el plugin camera_controls via widget
        widget = self.camera_grid.get_camera_widget(camera_id)
        auto_flash = False
        if widget and hasattr(widget, "_plugin_flash"):
            try:
                auto_flash = widget._plugin_flash["is_auto_flash_enabled"]()
            except Exception:
                auto_flash = False

        if auto_flash:
            self._capture_with_auto_flash(camera_id, thread, camera)
        else:
            frame = thread.capture_frame()
            if frame is None:
                frame = self._capture_with_shot(camera)
                if frame is None:
                    QMessageBox.warning(self, "Error", "No se pudo capturar")
                    return
            self._save_image(frame, camera)

    def _capture_with_auto_flash(self, camera_id: int, thread, camera):
        widget = self.camera_grid.get_camera_widget(camera_id)
        if widget and hasattr(widget, 'set_flash_state'):
            widget.set_flash_state(True)

        flash_success = thread.toggle_flash(True)
        if not flash_success:
            if widget and hasattr(widget, 'set_flash_state'):
                widget.set_flash_state(False)
            self._capture_normal(camera_id, thread, camera)
            return

        self.status_label.setText("⏱️ Flash encendido - Capturando en 2s...")
        flash_on_ms = advanced_config.get("flash_on_duration_ms", 2000)
        self._schedule_once(
            flash_on_ms,
            lambda: self._do_capture_with_flash(camera_id, thread, camera)
        )

    def _do_capture_with_flash(self, camera_id: int, thread, camera):
        frame = thread.capture_frame()
        if frame is None:
            frame = self._capture_with_shot(camera)
        if frame is None:
            self._turn_off_flash(camera_id, thread)
            QMessageBox.warning(self, "Error", "No se pudo capturar")
            return

        flash_off_ms = advanced_config.get("flash_off_duration_ms", 1000)
        self.status_label.setText(f"⏱️ Apagando flash en {flash_off_ms/1000:.1f}s...")

        from PySide6.QtCore import QEventLoop, QTimer
        loop = QEventLoop()
        QTimer.singleShot(flash_off_ms, loop.quit)
        loop.exec()

        self._turn_off_flash(camera_id, thread)
        self._save_image(frame, camera)

    def _turn_off_flash(self, camera_id: int, thread):
        thread.toggle_flash(False)
        widget = self.camera_grid.get_camera_widget(camera_id)
        if widget and hasattr(widget, 'set_flash_state'):
            widget.set_flash_state(False)
        self.status_label.setText("✅ Captura completada")

    def _capture_normal(self, camera_id: int, thread, camera):
        frame = thread.capture_frame()
        if frame is None:
            frame = self._capture_with_shot(camera)
        if frame is not None:
            self._save_image(frame, camera)

    def _capture_with_shot(self, camera: CameraDevice) -> Optional[np.ndarray]:
        try:
            url = f"http://{camera.ip}:{camera.port}/shot.jpg"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                img_array = np.frombuffer(response.content, np.uint8)
                return cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        except Exception as e:
            logger.debug(f"Error en shot: {e}")
        return None

    def _save_image(self, frame: np.ndarray, camera: CameraDevice):
        try:
            from ui.image_preview_dialog import ImagePreviewDialog
            dialog = ImagePreviewDialog(frame, camera.name, self)
            if dialog.exec() == QDialog.Accepted:
                filename, directory, use_default, frame = dialog.get_save_data()
                if not filename:
                    QMessageBox.warning(self, "Error", "Nombre vacío")
                    return
                settings = self.settings.get_capture_settings()
                full_path, size = self.file_manager.save_image(
                    frame, directory,
                    filename.replace(f".{settings.image_format.value}", ""),
                    settings.image_format, settings.image_quality,
                    settings.image_resolution
                )
                if full_path and os.path.exists(full_path):
                    if use_default:
                        settings.default_directory = directory
                        self.settings.save_capture_settings(settings)
                    self.file_explorer.refresh()
                    self.status_label.setText(f"📸 Foto guardada: {filename}")
                else:
                    QMessageBox.critical(self, "Error", "Error guardando")
        except Exception as e:
            logger.error(f"Error guardando imagen: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Error: {e}")

    def _on_capture_all(self):
        active_cameras = self.camera_manager.get_active_cameras()
        if not active_cameras:
            QMessageBox.warning(self, "Sin cámaras", "No hay cámaras activas")
            return

        saved_count = 0
        for camera in active_cameras:
            thread = self.camera_manager.get_thread(camera.id)
            if thread:
                frame = thread.capture_frame()
                if frame is not None:
                    self._save_image(frame, camera)
                    saved_count += 1

        self.file_explorer.refresh()
        self.status_label.setText(f"📸 Captura masiva: {saved_count} fotos")

    # ==================== GRABACIÓN ====================

    def _on_recording_toggle(self, camera_id: int, state: bool):
        if state:
            self._start_recording(camera_id)
        else:
            self._stop_recording(camera_id)

    def _start_recording(self, camera_id: int):
        camera = self.camera_manager.get_camera(camera_id)
        if not camera:
            return
        thread = self.camera_manager.get_thread(camera_id)
        if not thread:
            QMessageBox.warning(self, "Error", "No se encontró thread")
            return
        try:
            settings = self.settings.get_capture_settings()
            directory = os.path.expanduser(settings.default_directory)
            os.makedirs(directory, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            extension = settings.get_video_extension()
            filename = f"video_{timestamp}_{camera.name}{extension}"
            full_path = os.path.join(directory, filename)

            success = thread.start_recording(
                full_path, settings.video_codec, settings.video_fps
            )
            if success:
                self.status_label.setText(
                    f"🎬 Grabando: {camera.name} - "
                    f"{settings.video_resolution.display_name}"
                )
                widget = self.camera_grid.get_camera_widget(camera_id)
                if widget:
                    widget.set_status(CameraStatus.RECORDING)
            else:
                QMessageBox.critical(self, "Error", "Error iniciando grabación")
        except Exception as e:
            logger.error(f"Error grabando: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Error: {e}")

    def _stop_recording(self, camera_id: int):
        thread = self.camera_manager.get_thread(camera_id)
        if not thread:
            return
        try:
            file_path = thread.stop_recording()
            if file_path:
                self.status_label.setText(
                    f"⏹ Detenida: {os.path.basename(file_path)}"
                )
                self.file_explorer.refresh()
                widget = self.camera_grid.get_camera_widget(camera_id)
                if widget:
                    widget.set_status(CameraStatus.CONNECTED)
        except Exception as e:
            logger.error(f"Error deteniendo: {e}")

    def _on_record_all(self):
        self.is_recording_all = not self.is_recording_all
        if self.is_recording_all:
            self.record_all_btn.setText("⏹ Detener Todas")
            self.record_all_btn.setStyleSheet(
                self._get_toolbar_btn_style("#f44336", "#d32f2f")
            )
            self.camera_grid.start_all_recording()
        else:
            self.record_all_btn.setText("🎬 Grabar Todas")
            self.record_all_btn.setStyleSheet(
                self._get_toolbar_btn_style("#4CAF50", "#388E3C")
            )
            self.camera_grid.stop_all_recording()

    # ==================== FLASH ====================

    def _on_flash_toggle(self, camera_id: int, enabled: bool):
        camera = self.camera_manager.get_camera(camera_id)
        if not camera or camera.is_screen or camera.is_local:
            return
        thread = self.camera_manager.get_thread(camera_id)
        if not thread:
            return
        success = thread.toggle_flash(enabled)
        if success:
            self.status_label.setText(
                f"🔦 Flash {'encendido' if enabled else 'apagado'}: {camera.name}"
            )
        else:
            self.status_label.setText(f"⚠️ Error flash: {camera.name}")
            widget = self.camera_grid.get_camera_widget(camera_id)
            if widget:
                widget.set_flash_state(not enabled)

    def _on_auto_flash_toggled(self, camera_id: int, enabled: bool):
        camera = self.camera_manager.get_camera(camera_id)
        if not camera:
            return
        camera.auto_flash = enabled
        self.settings.save_camera(camera)
        status = "activado" if enabled else "desactivado"
        self.status_label.setText(f"⚡ Flash automático {status}: {camera.name}")

    # ==================== ARCHIVOS ====================

    def _on_file_selected(self, file_path: str):
        ext = os.path.splitext(file_path)[1].lower()
        image_exts = ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp']
        video_exts = ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.mpg', '.mpeg']

        if ext in image_exts:
            if self.video_preview.isVisible():
                self.video_preview.close_video()
            self.image_preview.set_image(file_path)
            self.status_label.setText(f"🖼️ {os.path.basename(file_path)}")
        elif ext in video_exts:
            if self.image_preview.isVisible():
                self.image_preview.hide()
            self.video_preview.load_video(file_path)
            self.status_label.setText(f"🎬 {os.path.basename(file_path)}")
        else:
            self.status_label.setText(f"📄 {os.path.basename(file_path)}")

    def _on_video_preview_closed(self):
        self.status_label.setText("Listo")

    # ==================== AUTO-CAPTURA ====================

    def _toggle_auto_capture(self, checked: bool):
        interval = advanced_config.get("auto_capture_interval", 5000)
        if checked:
            self.auto_capture_interval = interval
            self._tm.create(
                "main_window.auto_capture", self.auto_capture_interval,
                self._auto_capture, start=True
            )
            self.auto_capture_btn.setText("🔄 Detener Auto")
        else:
            self._tm.stop("main_window.auto_capture")
            self.auto_capture_btn.setText("🔄 Auto")

    def _auto_capture(self):
        self._on_capture_all()

    # ==================== CONFIGURACIÓN ====================

    def _show_settings(self):
        dialog = SettingsDialog(self)
        dialog.settings_changed.connect(self._on_settings_changed)
        dialog.exec()

    def _on_settings_changed(self, report=None, modules=None):
        logger.info("⚙️ Aplicando cambios de configuración...")

        if report is None:
            settings_manager.invalidate_advanced_cache()
            settings_manager.invalidate_detection_cache()
            settings_manager.invalidate_scan_cache()
            settings_manager.invalidate_capture_cache()
            self.status_label.setText("⚙️ Configuración actualizada")
            return

        advanced_config.reload()
        logger.info(f"  ✅ Config recargada ({advanced_config.count()} params)")

        from utils.change_detector import ReloadLevel

        if report.level == ReloadLevel.NONE:
            self.status_label.setText("⚙️ Sin cambios")
            return

        if report.level == ReloadLevel.CONFIG_ONLY:
            self.file_explorer.refresh()
            self._propagate_config_to_threads()
            self.status_label.setText("⚙️ Configuración actualizada")
            return

        if report.level == ReloadLevel.HOT_RELOAD:
            self._reload_enhancer_only()
            self._apply_hot_reload(modules or {})
            self.status_label.setText(
                f"⚙️ Aplicado en caliente: {', '.join(report.categories)}"
            )
            return

        if report.level == ReloadLevel.RESTART_AFFECTED:
            self._schedule_once(
                50,
                lambda: self._restart_affected_cameras(report.affected_cameras)
            )
            self.status_label.setText("⚙️ Reiniciando cámaras...")
            return

        if report.level == ReloadLevel.RESTART_ALL:
            self.file_explorer.refresh()
            self._propagate_config_to_threads()
            self._schedule_once(50, self._reload_cameras_async)
            self.status_label.setText("⚙️ Reiniciando configuración...")
            return

        self.file_explorer.refresh()

    def _apply_hot_reload(self, modules: dict):
        changed_modules = list(modules.keys())
        logger.info(f"  🔄 Hot reload de módulos: {changed_modules}")

        # FileManager
        if "file_manager" in modules:
            try:
                if hasattr(self.file_manager, 'reload_config'):
                    self.file_manager.reload_config()
            except Exception as e:
                logger.warning(f"  ⚠️ Error FileManager: {e}")

        # Throttle
        if "throttle" in modules:
            for camera_id, thread in list(self.camera_threads.items()):
                try:
                    if hasattr(thread, '_adaptive_throttle') and thread._adaptive_throttle:
                        t = thread._adaptive_throttle
                        cfg = advanced_config.get_all()
                        t.target_cpu = cfg.get("throttle_target_cpu", 1.5)
                        t.target_gpu = cfg.get("throttle_target_gpu", 0.80)
                        t.max_skip = cfg.get("throttle_max_skip", 3)
                        t.check_interval = cfg.get("throttle_check_interval", 1.0)
                        if hasattr(t, 'hysteresis'):
                            t.hysteresis = cfg.get("throttle_hysteresis", 0.30)
                except Exception as e:
                    logger.debug(f"  ⚠️ Error throttle {camera_id}: {e}")

        # Motion / Face / Scan → recargar analyzers
        if any(m in modules for m in ("motion", "face", "scan")):
            self._reload_detection_settings_only()
            self._refresh_frame_analyzers()

        # UI
        if "ui" in modules:
            cfg = advanced_config.get_all()
            for widget in self.camera_grid.get_camera_widgets():
                try:
                    widget._apply_config_update(cfg)
                except Exception:
                    pass
            try:
                spacing = cfg.get("grid_spacing", 12)
                margins = cfg.get("grid_margins", 8)
                self.camera_grid.grid_layout.setSpacing(spacing)
                self.camera_grid.grid_layout.setContentsMargins(
                    margins, margins, margins, margins
                )
            except Exception:
                pass

        # Audio
        if "audio" in modules:
            try:
                if hasattr(audio_manager, 'reload_config'):
                    audio_manager.reload_config()
            except Exception:
                pass

        # Notifications
        if "notifications" in modules:
            try:
                from notifications.notification_manager import notification_manager
                cfg = advanced_config.get_all()
                notification_manager.min_interval_seconds = cfg.get(
                    "notification_min_interval", 30
                )
            except Exception:
                pass

        # System Monitor
        if "system_monitor" in modules:
            try:
                cfg = advanced_config.get_all()
                system_monitor._poll_interval = cfg.get(
                    "system_monitor_interval", 1.0
                )
            except Exception:
                pass

        # Thumbnail
        if "thumbnail" in modules:
            try:
                from ui.video_thumbnail_worker import video_thumbnail_manager
                cfg = advanced_config.get_all()
                video_thumbnail_manager.thread_pool.setMaxThreadCount(
                    cfg.get("video_thumbnail_workers", 2)
                )
            except Exception:
                pass

    def _refresh_frame_analyzers(self):
        """Fuerza a los threads a recargar FrameAnalyzers."""
        logger.info("🔄 Recargando FrameAnalyzers...")
        for camera_id, thread in list(self.camera_threads.items()):
            try:
                if hasattr(thread, "refresh_analyzers"):
                    thread.refresh_analyzers()
            except Exception as e:
                logger.debug(f"Error refresh analyzers {camera_id}: {e}")

        # Cámaras locales
        for camera_id in list(self.camera_manager.local_camera_ids):
            thread = self.camera_manager.local_manager.get_thread(camera_id)
            if thread and hasattr(thread, "refresh_analyzers"):
                try:
                    thread.refresh_analyzers()
                except Exception:
                    pass

    def on_plugin_state_changed(self, plugin_name: str, enabled: bool):
        """Callback para cuando un plugin cambia de estado."""
        detection_plugins = {
            "motion_detector", "face_recognizer", "document_scanner"
        }
        if plugin_name in detection_plugins:
            logger.info(
                f"🔄 Plugin '{plugin_name}' "
                f"{'activado' if enabled else 'desactivado'} "
                f"→ recargando analyzers"
            )
            self._refresh_frame_analyzers()

    def _restart_affected_cameras(self, camera_ids: list):
        for camera_id in camera_ids:
            if camera_id not in self.camera_threads:
                continue
            logger.info(f"  🔄 Reiniciando cámara {camera_id}")
            thread = self.camera_threads[camera_id]
            try:
                thread.frame_ready.disconnect()
                thread.status_changed.disconnect()
                thread.error_occurred.disconnect()
                for sig in ['motion_detected', 'face_detected',
                            'document_detected', 'text_recognized']:
                    if hasattr(thread, sig):
                        try:
                            getattr(thread, sig).disconnect()
                        except Exception:
                            pass
            except Exception:
                pass

            camera = self.camera_manager.get_camera(camera_id)
            if camera is None:
                continue
            try:
                self.camera_manager.remove_camera(camera_id)
            except Exception as e:
                logger.error(f"Error removiendo cámara: {e}")
            del self.camera_threads[camera_id]
            self.camera_grid.remove_camera_widget(camera_id)
            self._add_camera(camera)

    def _propagate_config_to_threads(self):
        cfg = advanced_config.get_all()

        for camera_id, thread in list(self.camera_threads.items()):
            try:
                # Throttle
                if hasattr(thread, '_adaptive_throttle') and thread._adaptive_throttle:
                    throttle = thread._adaptive_throttle
                    if cfg.get("throttle_enabled", True):
                        throttle.target_cpu = cfg.get("throttle_target_cpu", 1.5)
                        throttle.target_gpu = cfg.get("throttle_target_gpu", 0.80)
                        throttle.max_skip = cfg.get("throttle_max_skip", 3)
                        throttle.check_interval = cfg.get("throttle_check_interval", 1.0)
                        if hasattr(throttle, 'hysteresis'):
                            throttle.hysteresis = cfg.get("throttle_hysteresis", 0.30)
                    else:
                        throttle.target_cpu = 999.0
                        throttle.target_gpu = 999.0
                        throttle.max_skip = 0

                # FPS
                if hasattr(thread, 'fps'):
                    new_fps = cfg.get("target_fps", 30)
                    if hasattr(thread, 'camera') and thread.camera.is_screen:
                        new_fps = cfg.get("screen_max_fps", 30)
                    thread.fps = new_fps
                    if hasattr(thread, '_frame_scheduler'):
                        thread._frame_scheduler.set_fps(new_fps)

                # Skip
                if hasattr(thread, '_detection_frame_skip'):
                    thread._detection_frame_skip = cfg.get("detection_frame_skip", 3)
                if hasattr(thread, '_scan_frame_skip'):
                    thread._scan_frame_skip = cfg.get("scan_frame_skip", 5)

                # Red
                if hasattr(thread, 'max_reconnect_attempts'):
                    thread.max_reconnect_attempts = cfg.get("reconnect_attempts", 3)
                if hasattr(thread, '_frame_timeout'):
                    thread._frame_timeout = cfg.get("frame_timeout", 5.0)
                if hasattr(thread, '_connection_timeout'):
                    thread._connection_timeout = cfg.get("connection_timeout", 2.0)
                if hasattr(thread, '_read_timeout'):
                    thread._read_timeout = cfg.get("read_timeout", 2.0)
                if hasattr(thread, '_reconnect_delay'):
                    thread._reconnect_delay = cfg.get("reconnect_delay", 0.5)

                # Recargar config general
                if hasattr(thread, 'reload_config'):
                    try:
                        thread.reload_config()
                    except Exception:
                        pass

            except Exception as e:
                logger.error(f"Error propagando config a cámara {camera_id}: {e}")

        # FileManager
        try:
            if hasattr(self.file_manager, 'reload_config'):
                self.file_manager.reload_config()
        except Exception:
            pass

        # AudioManager
        try:
            if hasattr(audio_manager, 'reload_config'):
                audio_manager.reload_config()
        except Exception:
            pass

    def _reload_detection_settings_only(self):
        advanced_config.reload()
        # FASE 3: forzar reload de analyzers (los analyzers leen config ellos mismos)
        try:
            from core.extension_registry import get_extension_registry
            from core.extensions.interfaces import FrameAnalyzer
            registry = get_extension_registry()
            for a in registry.get(FrameAnalyzer):
                if hasattr(a, 'reload_config'):
                    try:
                        a.reload_config()
                    except Exception:
                        pass
        except Exception:
            pass

    def _reload_scan_only(self):
        # FASE 3: ya cubierto por reload_config del DocumentAnalyzer
        pass

    def _reload_enhancer_only(self):
        try:
            from detection.image_enhancer import ImageEnhancer
            if hasattr(ImageEnhancer, 'reload_config'):
                ImageEnhancer.reload_config()
        except Exception:
            pass

    def _clear_all_data(self):
        reply = QMessageBox.question(
            self, "Confirmar", "¿Limpiar toda la configuración?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.settings.clear_all()
            self._schedule_once(50, self._reload_cameras_async)
            self.status_label.setText("🗑️ Datos limpiados")

    # ==================== UTILIDADES ====================

    def _set_quality(self, value: int):
        settings = self.settings.get_capture_settings()
        settings.image_quality = value
        self.settings.save_capture_settings(settings)
        self.quality_combo.setText(f"{value}%")

    def _toggle_file_explorer(self, visible: bool):
        self.file_explorer.setVisible(visible)

    def _refresh_view(self):
        self.file_explorer.refresh()
        self.status_label.setText("🔄 Refrescando...")
        self._schedule_once(50, self._reload_cameras_async)

    def _reload_cameras_async(self):
        for widget in self.camera_grid.get_camera_widgets():
            widget.setVisible(False)
        self.camera_grid.clear_all_widgets()
        self.capture_settings = self.settings.get_capture_settings()
        self.file_manager = FileManager(self.capture_settings)
        self._schedule_once(100, self._do_reload_cameras)

    def _do_reload_cameras(self):
        self.camera_manager.stop_all()
        self.camera_threads.clear()
        self._load_cameras_deferred()

    def _new_project(self):
        self.file_explorer.refresh()
        self.status_label.setText("📁 Nuevo proyecto")

    def _update_status(self):
        active_count = len(self.camera_manager.get_active_cameras())
        total_count = len(self.camera_manager.cameras)
        self.cameras_count.setText(f"{active_count}/{total_count} cámaras")

    def _load_ui_state(self):
        ui_settings = self.settings.get_ui_settings()
        if ui_settings.get("geometry"):
            try:
                self.restoreGeometry(ui_settings["geometry"])
            except Exception:
                pass
        columns = ui_settings.get("camera_grid_columns", 2)
        self.camera_grid.set_columns(columns)

    def _on_camera_removed(self, camera_id: int):
        logger.info(f"🗑️ Eliminando cámara {camera_id}")

        widget = self.camera_grid.get_camera_widget(camera_id)
        if widget:
            widget.setVisible(False)
            if hasattr(widget, 'cleanup'):
                widget.cleanup()

        self.status_label.setText(f"⏹ Cerrando cámara {camera_id}...")

        if camera_id in self.camera_threads:
            thread = self.camera_threads[camera_id]
            try:
                thread.frame_ready.disconnect()
                thread.status_changed.disconnect()
                thread.error_occurred.disconnect()
                for sig in ['motion_detected', 'face_detected',
                            'document_detected', 'text_recognized']:
                    if hasattr(thread, sig):
                        try:
                            getattr(thread, sig).disconnect()
                        except Exception:
                            pass
            except Exception:
                pass
            del self.camera_threads[camera_id]

        def worker():
            try:
                self.camera_manager.remove_camera(camera_id)
            except Exception as e:
                logger.error(f"Error cerrando cámara: {e}")
            self.camera_removal_finished.emit(camera_id)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_camera_removal(self, camera_id: int):
        try:
            self.camera_grid.remove_camera_widget(camera_id)
            self.settings.remove_camera(camera_id)
            self._update_status()
            self.status_label.setText("📷 Cámara eliminada")

            pending = self.settings.get_cameras()
            loaded_ids = set(self.camera_grid.cameras.keys())
            for cam in pending:
                if cam.id not in loaded_ids:
                    self._add_camera(cam)
        except Exception as e:
            logger.error(f"Error finalizando eliminación: {e}")

    def _schedule_once(self, delay_ms: int, callback):
        name = f"main_window.once_{id(callback)}_{int(time.time() * 1000)}"
        for existing in list(self._tm.list_timers()):
            if existing.startswith(f"main_window.once_{id(callback)}_"):
                self._tm.stop(existing)
        self._tm.create(name, delay_ms, callback, single_shot=True, start=True)

    def keyPressEvent(self, event):
        try:
            from core.extension_registry import get_extension_registry
            from core.extensions.interfaces import KeyboardInterceptor
            registry = get_extension_registry()
            for interceptor in registry.get(KeyboardInterceptor):
                try:
                    if interceptor.intercept(event.key(), int(event.modifiers())):
                        event.accept()
                        return
                except Exception as e:
                    logger.debug(f"Error en KeyboardInterceptor: {e}")
        except Exception:
            pass
        super().keyPressEvent(event)

    # ==================== CIERRE ORDENADO ====================

    def closeEvent(self, event):
        if self._is_closing:
            event.accept()
            return

        logger.info("🛑 Cerrando aplicación...")
        self._is_closing = True
        self.hide()

        # ShutdownHooks
        try:
            from core.extension_registry import get_extension_registry
            from core.extensions.interfaces import ShutdownHook
            registry = get_extension_registry()
            hooks = sorted(
                registry.get(ShutdownHook),
                key=lambda h: h.get_priority() if hasattr(h, 'get_priority') else 50,
                reverse=True,
            )
            for hook in hooks:
                try:
                    hook.on_shutdown()
                except Exception as e:
                    logger.error(f"❌ ShutdownHook falló: {e}")
        except Exception:
            pass

        try:
            self._tm.stop_all()
        except Exception as e:
            logger.error(f"Error deteniendo timers: {e}")

        try:
            from ui.video_thumbnail_worker import video_thumbnail_manager
            video_thumbnail_manager.cleanup()
        except Exception:
            pass

        try:
            if hasattr(self, 'video_preview') and self.video_preview:
                self.video_preview.close_video()
        except Exception:
            pass

        try:
            if hasattr(self, 'system_monitor_widget'):
                self.system_monitor_widget.cleanup()
            system_monitor.stop()
        except Exception:
            pass

        try:
            audio_manager.stop_all()
        except Exception:
            pass

        try:
            ui_settings = {
                "geometry": self.saveGeometry(),
                "camera_grid_columns": self.camera_grid.columns
            }
            self.settings.save_ui_settings(ui_settings)
        except Exception:
            pass

        event.accept()

        def close_background():
            try:
                for camera_id in list(self.camera_threads.keys()):
                    try:
                        thread = self.camera_threads[camera_id]
                        if thread.is_recording():
                            thread.stop_recording()
                        thread.disconnect_camera()
                        thread.stop()
                    except Exception as e:
                        logger.error(f"Error cerrando cámara {camera_id}: {e}")

                try:
                    self.camera_manager.stop_all()
                except Exception as e:
                    logger.error(f"Error en camera_manager.stop_all: {e}")

                self.camera_threads.clear()
                logger.info("✅ Aplicación cerrada")
            except Exception as e:
                logger.error(f"Error en cierre global: {e}", exc_info=True)

        threading.Thread(target=close_background, daemon=True).start()

    def reject(self):
        try:
            if timer_manager.exists(self._DEFERRED_TIMER_NAME):
                timer_manager.stop(self._DEFERRED_TIMER_NAME)
        except Exception:
            pass
        super().reject()