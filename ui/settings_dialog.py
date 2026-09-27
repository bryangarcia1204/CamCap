"""
Diálogo de configuración - REFACTORIZADO para plugins.

Estructura:
- Tabs CORE: Cámaras, Captura, Apariencia, Sistema, Debug, Avanzado
- Tabs de PLUGIN: se cargan dinámicamente desde ExtensionRegistry
- Los plugins se auto-registran/des-registran en on_enable/on_disable
"""
import os
from typing import Dict, Any
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                               QTabWidget, QWidget, QFormLayout,
                               QLineEdit, QComboBox, QSpinBox,
                               QPushButton, QLabel, QListWidget,
                               QListWidgetItem, QMessageBox, QFileDialog,
                               QGroupBox, QSlider, QGridLayout, QCheckBox,
                               QDoubleSpinBox, QScrollArea, QInputDialog)
from PySide6.QtCore import Qt, Signal

from ui.loading_manager import LoadingManager
from core.models import (CameraDevice, ImageFormat, VideoFormat,
                    CaptureSettings, Resolution)
from utils.timer_manager import timer_manager
from core.settings_manager import settings_manager
from utils.config_loader import AdvancedConfig
from utils.logger import get_logger

logger = get_logger("SettingsDialog")


class SettingsDialog(QDialog):
    settings_changed = Signal(object, object)

    _DEFERRED_TIMER_NAME = "settings_dialog.deferred_advanced_tab"

    def __init__(self, parent=None):
        super().__init__(parent)
        logger.debug("🔧 [init] SettingsDialog: iniciando construcción")

        self.setWindowTitle("Configuración")
        self.setMinimumSize(950, 780)
        self._editing_camera_id = -1
        self._tabs_ref = None
        self._advanced_tab_loaded = False
        self._plugin_tab_indices = {}   # tab_id → índice
        self.change_counter_camera = settings_manager._settings.value(
            "cameras/count", 0
        )

        # 1. Esqueleto + tabs core
        self._setup_ui()
        logger.debug("🔧 [init] Esqueleto UI listo")

        # 2. Cargar pestañas básicas
        self._load_settings()
        logger.debug("🔧 [init] Pestañas básicas cargadas")

    # ==================== ESTRUCTURA BASE ====================

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        self._tabs_ref = QTabWidget()

        # === TABS CORE (siempre visibles) ===
        self._tabs_ref.addTab(self._create_cameras_tab(), "📷 Cámaras")
        self._tabs_ref.addTab(self._create_capture_tab(), "⚙️ Captura")
        self._tabs_ref.addTab(self._create_appearance_tab(), "🎨 Apariencia")
        self._tabs_ref.addTab(self._create_system_tab(), "🔧 Sistema")
        self._tabs_ref.addTab(self._create_plugins_tab(), "🔌 Plugins")
        self._tabs_ref.addTab(self._create_debug_tab(), "🐛 Debug")

        # === TABS DE PLUGINS (dinámicas) ===
        # Se insertan ANTES de la última tab (Debug)
        self._add_plugin_tabs()

        layout.addWidget(self._tabs_ref)

        # === BOTONES ===
        buttons = QHBoxLayout()
        buttons.addStretch()

        save_btn = QPushButton("💾 Guardar")
        save_btn.clicked.connect(self._save_settings)
        buttons.addWidget(save_btn)

        cancel_btn = QPushButton("❌ Cancelar")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)

        layout.addLayout(buttons)

    def _create_plugins_tab(self) -> QWidget:
        """Tab que muestra el botón para abrir el Plugin Manager."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(20)

        # Icono grande
        icon = QLabel("🔌")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size: 64px;")
        layout.addWidget(icon)

        # Título
        title = QLabel("Administrador de Plugins")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size: 20px; font-weight: bold; color: #4da0c4;"
        )
        layout.addWidget(title)

        # Descripción
        desc = QLabel(
            "Activa, desactiva e instala plugins para ProCamera.\n"
            "Consulta capabilities, dependencias y extensiones de cada plugin."
        )
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet(
            "color: rgba(255,255,255,0.7); font-size: 13px;"
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Stats
        try:
            from core.plugin_api import get_plugin_manager
            pm = get_plugin_manager()
            if pm is not None:
                stats = pm.get_stats()
                stats_text = (
                    f"📊 {stats['total']} plugins instalados  ·  "
                    f"✅ {stats['enabled']} activos"
                )
                if stats['failed'] > 0:
                    stats_text += f"  ·  ❌ {stats['failed']} fallidos"
                stats_lbl = QLabel(stats_text)
                stats_lbl.setAlignment(Qt.AlignCenter)
                stats_lbl.setStyleSheet(
                    "color: rgba(255,255,255,0.6); font-size: 12px;"
                )
                layout.addWidget(stats_lbl)
        except Exception:
            pass

        # Botón
        open_btn = QPushButton("🔌 Abrir Administrador de Plugins")
        open_btn.setMinimumHeight(45)
        open_btn.setMinimumWidth(280)
        open_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1a237e, stop:1 #4a148c);
                color: white;
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 50px;
                padding: 12px 32px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #283593, stop:1 #6a1b9a);
            }
        """)
        open_btn.clicked.connect(self._open_plugin_manager)
        layout.addWidget(open_btn, alignment=Qt.AlignCenter)

        layout.addStretch()
        return widget

    def _open_plugin_manager(self):
        """Abre el Plugin Manager."""
        from ui.plugin_manager_dialog import PluginManagerDialog

        dialog = PluginManagerDialog(self)
        dialog.plugins_changed.connect(self._on_plugins_changed)
        dialog.exec()

    def _on_plugins_changed(self):
        """Callback cuando cambian los plugins."""
        # Cerrar este diálogo para forzar recarga
        self.accept()

    def _add_plugin_tabs(self):
        """
        Añade tabs de plugins ACTIVOS desde el ExtensionRegistry.

        Los plugins solo registran su ConfigTab en `on_enable()`,
        así que `registry.get(ConfigTab)` solo devuelve los activos.

        Se insertan antes de la última tab (Debug).
        """
        try:
            from core.extension_registry import get_extension_registry
            registry = get_extension_registry()
        except Exception as e:
            logger.debug(f"⚠️ Registry no disponible: {e}")
            return

        try:
            from core.extensions.interfaces import ConfigTab

            config_tabs = registry.get(ConfigTab)
            if not config_tabs:
                logger.debug("ℹ️ No hay ConfigTabs de plugins registradas")
                return

            # Insertar antes de la última tab (Debug)
            insert_index = self._tabs_ref.count() - 1

            for tab in config_tabs:
                try:
                    title = tab.get_title()
                    icon = tab.get_icon()
                    widget = tab.get_widget()

                    if widget is None:
                        logger.debug(f"⚠️ ConfigTab '{title}' sin widget, saltando")
                        continue

                    full_title = f"{icon} {title}".strip() if icon else title

                    self._tabs_ref.insertTab(insert_index, widget, full_title)
                    self._plugin_tab_indices[tab.get_id()] = insert_index
                    insert_index += 1

                    logger.debug(f"🎨 ConfigTab añadida: '{full_title}'")

                except Exception as e:
                    logger.error(f"❌ Error añadiendo ConfigTab: {e}", exc_info=True)

            logger.info(f"🎨 {len(config_tabs)} ConfigTab(s) de plugin añadida(s)")

        except Exception as e:
            logger.debug(f"⚠️ Error cargando ConfigTabs: {e}")

    # ==================== PESTAÑA CÁMARAS ====================

    def _create_cameras_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.camera_list = QListWidget()
        self.camera_list.setStyleSheet("QListWidget { min-height: 200px; }")
        layout.addWidget(QLabel("Cámaras configuradas:"))
        layout.addWidget(self.camera_list)

        btns = QHBoxLayout()
        add_btn = QPushButton("➕ IP")
        add_btn.clicked.connect(self._add_camera)
        btns.addWidget(add_btn)

        edit_btn = QPushButton("✏️ Editar")
        edit_btn.clicked.connect(self._edit_camera)
        btns.addWidget(edit_btn)

        remove_btn = QPushButton("❌ Eliminar")
        remove_btn.clicked.connect(self._remove_camera)
        btns.addWidget(remove_btn)

        add_screen_btn = QPushButton("🖥️ Pantalla")
        add_screen_btn.clicked.connect(self._add_screen_camera)
        btns.addWidget(add_screen_btn)

        add_local_btn = QPushButton("📹 Local")
        add_local_btn.clicked.connect(self._add_local_camera)
        btns.addWidget(add_local_btn)

        btns.addStretch()
        layout.addLayout(btns)

        edit_group = QGroupBox("Editar cámara")
        edit_layout = QFormLayout(edit_group)

        self.cam_name_edit = QLineEdit()
        edit_layout.addRow("Nombre:", self.cam_name_edit)

        self.cam_ip_edit = QLineEdit()
        edit_layout.addRow("IP:", self.cam_ip_edit)

        self.cam_port_edit = QSpinBox()
        self.cam_port_edit.setRange(1, 65535)
        self.cam_port_edit.setValue(4747)
        edit_layout.addRow("Puerto:", self.cam_port_edit)

        self.cam_url_type = QComboBox()
        self.cam_url_type.addItems(["video", "shot"])
        edit_layout.addRow("URL tipo:", self.cam_url_type)

        self.cam_save_btn = QPushButton("Guardar Cámara")
        self.cam_save_btn.clicked.connect(self._save_camera_edit)
        edit_layout.addRow("", self.cam_save_btn)

        layout.addWidget(edit_group)
        return widget

    def _add_screen_camera(self):
        cameras = settings_manager.get_cameras()
        if any(c.is_screen for c in cameras):
            QMessageBox.warning(self, "Error", "Ya existe cámara de pantalla")
            return
        camera = CameraDevice(id=-1, name="Pantalla", ip="SCREEN",
                              port=0, url_type="screen", is_screen=True)
        if settings_manager.save_camera(camera):
            self._update_camera_list(settings_manager.get_cameras())
            QMessageBox.information(self, "Éxito", "Cámara pantalla añadida")

    def _add_local_camera(self):
        from core.engine.local_camera_engine import LocalCameraDetector
        LoadingManager.show_loading("Detectando cámaras...", "Buscando dispositivos")
        try:
            available = LocalCameraDetector.detect_available_cameras()
        finally:
            LoadingManager.hide_loading()

        if not available:
            QMessageBox.warning(self, "Sin cámaras", "No se detectaron cámaras locales")
            return

        items = [f"{c.name} (índice {c.index})" for c in available]
        item, ok = QInputDialog.getItem(self, "Seleccionar Cámara",
                                        "Cámaras detectadas:", items, 0, False)
        if ok and item:
            idx = items.index(item)
            info = available[idx]
            cameras = settings_manager.get_cameras()
            if any(c.is_local and c.camera_index == info.index for c in cameras):
                QMessageBox.warning(self, "Error", f"Índice {info.index} ya configurado")
                return
            camera = CameraDevice(id=-1, name=f"Cámara Local {info.index}",
                                  ip="LOCAL", port=0, url_type="local",
                                  is_local=True, camera_index=info.index)
            if settings_manager.save_camera(camera):
                self._update_camera_list(settings_manager.get_cameras())
                QMessageBox.information(self, "Éxito", f"Cámara {info.index} añadida")

    def _add_camera(self):
        self.cam_name_edit.clear()
        self.cam_ip_edit.clear()
        self.cam_port_edit.setValue(4747)
        self.cam_url_type.setCurrentText("video")
        self.cam_save_btn.setText("Agregar Cámara")
        self._editing_camera_id = -1

    def _edit_camera(self):
        current = self.camera_list.currentItem()
        if not current:
            return
        camera_id = current.data(Qt.UserRole)
        cameras = settings_manager.get_cameras()
        camera = next((c for c in cameras if c.id == camera_id), None)
        if camera and not camera.is_screen and not camera.is_local:
            self.cam_name_edit.setText(camera.name)
            self.cam_ip_edit.setText(camera.ip)
            self.cam_port_edit.setValue(camera.port)
            self.cam_url_type.setCurrentText(camera.url_type)
            self.cam_save_btn.setText("Actualizar Cámara")
            self._editing_camera_id = camera_id

    def _save_camera_edit(self):
        name = self.cam_name_edit.text().strip()
        ip = self.cam_ip_edit.text().strip()
        port = self.cam_port_edit.value()
        url_type = self.cam_url_type.currentText()
        if not name or not ip:
            QMessageBox.warning(self, "Error", "Nombre e IP obligatorios")
            return
        camera = CameraDevice(
            id=self._editing_camera_id if hasattr(self, '_editing_camera_id') else -1,
            name=name, ip=ip, port=port, url_type=url_type
        )
        if settings_manager.save_camera(camera):
            self._update_camera_list(settings_manager.get_cameras())
            self.cam_save_btn.setText("Guardar Cámara")
            QMessageBox.information(self, "Éxito", "Cámara guardada")

    def _remove_camera(self):
        current = self.camera_list.currentItem()
        if not current:
            return
        camera_id = current.data(Qt.UserRole)
        reply = QMessageBox.question(self, "Confirmar", "¿Eliminar cámara?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            if settings_manager.remove_camera(camera_id):
                self._update_camera_list(settings_manager.get_cameras())

    def _update_camera_list(self, cameras):
        self.camera_list.clear()
        for cam in cameras:
            icon = "🖥️" if cam.is_screen else ("📹" if cam.is_local else "📷")
            item = QListWidgetItem(f"{icon} {cam.name}")
            item.setData(Qt.UserRole, cam.id)
            self.camera_list.addItem(item)

    # ==================== PESTAÑA CAPTURA ====================

    def _create_capture_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(16)

        img_group = QGroupBox("📸 Imágenes")
        img_layout = QGridLayout(img_group)

        img_layout.addWidget(QLabel("Formato:"), 0, 0)
        self.img_format = QComboBox()
        self.img_format.addItems([f.value.upper() for f in ImageFormat])
        img_layout.addWidget(self.img_format, 0, 1)

        img_layout.addWidget(QLabel("Resolución:"), 1, 0)
        self.img_resolution = QComboBox()
        self.img_resolution.addItems([r.display_name for r in Resolution])
        img_layout.addWidget(self.img_resolution, 1, 1)

        img_layout.addWidget(QLabel("Calidad:"), 2, 0)
        q_layout = QHBoxLayout()
        self.img_quality_slider = QSlider(Qt.Horizontal)
        self.img_quality_slider.setRange(1, 100)
        self.img_quality_slider.setValue(85)
        self.img_quality_slider.valueChanged.connect(
            lambda v: self.img_quality_label.setText(f"{v}%"))
        q_layout.addWidget(self.img_quality_slider)
        self.img_quality_label = QLabel("85%")
        q_layout.addWidget(self.img_quality_label)
        img_layout.addLayout(q_layout, 2, 1)

        layout.addWidget(img_group)

        video_group = QGroupBox("🎬 Videos")
        video_layout = QGridLayout(video_group)

        video_layout.addWidget(QLabel("Formato:"), 0, 0)
        self.vid_format = QComboBox()
        self.vid_format.addItems([f.value.upper() for f in VideoFormat])
        self.vid_format.currentTextChanged.connect(self._update_codecs)
        video_layout.addWidget(self.vid_format, 0, 1)

        video_layout.addWidget(QLabel("Códec:"), 1, 0)
        self.vid_codec = QComboBox()
        video_layout.addWidget(self.vid_codec, 1, 1)

        video_layout.addWidget(QLabel("Resolución:"), 2, 0)
        self.vid_resolution = QComboBox()
        self.vid_resolution.addItems([r.display_name for r in Resolution])
        video_layout.addWidget(self.vid_resolution, 2, 1)

        video_layout.addWidget(QLabel("FPS:"), 3, 0)
        self.vid_fps = QSpinBox()
        self.vid_fps.setRange(10, 60)
        self.vid_fps.setValue(30)
        video_layout.addWidget(self.vid_fps, 3, 1)

        video_layout.addWidget(QLabel("Calidad:"), 4, 0)
        vq_layout = QHBoxLayout()
        self.vid_quality_slider = QSlider(Qt.Horizontal)
        self.vid_quality_slider.setRange(1, 100)
        self.vid_quality_slider.setValue(80)
        self.vid_quality_slider.valueChanged.connect(
            lambda v: self.vid_quality_label.setText(f"{v}%"))
        vq_layout.addWidget(self.vid_quality_slider)
        self.vid_quality_label = QLabel("80%")
        vq_layout.addWidget(self.vid_quality_label)
        video_layout.addLayout(vq_layout, 4, 1)

        layout.addWidget(video_group)

        file_group = QGroupBox("📁 Archivos")
        file_layout = QFormLayout(file_group)

        self.default_name = QLineEdit("foto_{timestamp}")
        file_layout.addRow("Nombre:", self.default_name)

        self.default_dir = QLineEdit(os.path.expanduser("~/Pictures/Capturas"))
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(self.default_dir)
        browse_btn = QPushButton("📁")
        browse_btn.clicked.connect(self._browse_default_dir)
        dir_layout.addWidget(browse_btn)
        file_layout.addRow("Directorio:", dir_layout)

        layout.addWidget(file_group)
        layout.addStretch()
        return widget

    def _update_codecs(self, format_name: str):
        codecs_map = {
            "AVI": ["MJPG", "XVID", "DIVX", "I420"],
            "MP4": ["mp4v", "X264", "H264", "avc1"],
            "MKV": ["X264", "XVID", "MJPG"],
            "MOV": ["mp4v", "jpeg", "MJPG"],
            "MPG": ["MPEG", "MPEG1", "MJPG"],
        }
        codecs = codecs_map.get(format_name.upper(), ["MJPG"])
        self.vid_codec.clear()
        self.vid_codec.addItems(codecs)

    def _browse_default_dir(self):
        path = QFileDialog.getExistingDirectory(
            self, "Seleccionar Directorio", self.default_dir.text())
        if path:
            self.default_dir.setText(path)

    # ==================== PESTAÑA APARIENCIA ====================

    def _create_appearance_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        theme_group = QGroupBox("Tema")
        theme_layout = QFormLayout(theme_group)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Oscuro", "Claro", "Sistema"])
        theme_layout.addRow("Tema:", self.theme_combo)

        layout.addWidget(theme_group)

        grid_group = QGroupBox("Grid de cámaras")
        grid_layout = QFormLayout(grid_group)

        self.grid_columns = QSpinBox()
        self.grid_columns.setRange(1, 4)
        self.grid_columns.setValue(2)
        grid_layout.addRow("Columnas:", self.grid_columns)

        layout.addWidget(grid_group)
        layout.addStretch()
        return widget

    # ==================== PESTAÑA SISTEMA ====================

    def _create_system_tab(self) -> QWidget:
        """Sistema: FPS, throttle, red, sistema, video preview."""
        widget = QWidget()
        main_layout = QVBoxLayout(widget)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)

        # ========== FPS / Rendimiento ==========
        fps_group = QGroupBox("🎬 FPS / Rendimiento")
        fps_layout = QGridLayout(fps_group)
        fps_layout.setVerticalSpacing(10)
        fps_layout.setHorizontalSpacing(20)

        fps_layout.addWidget(QLabel("FPS objetivo:"), 0, 0)
        self.adv_target_fps = QSpinBox()
        self.adv_target_fps.setRange(1, 120)
        self.adv_target_fps.setValue(30)
        self.adv_target_fps.setSuffix(" FPS")
        fps_layout.addWidget(self.adv_target_fps, 0, 1)

        fps_layout.addWidget(QLabel("FPS máx. pantalla:"), 1, 0)
        self.adv_screen_max_fps = QSpinBox()
        self.adv_screen_max_fps.setRange(1, 120)
        self.adv_screen_max_fps.setValue(30)
        self.adv_screen_max_fps.setSuffix(" FPS")
        fps_layout.addWidget(self.adv_screen_max_fps, 1, 1)

        fps_layout.addWidget(QLabel("Buffer de captura:"), 2, 0)
        self.adv_buffer_size = QSpinBox()
        self.adv_buffer_size.setRange(1, 30)
        self.adv_buffer_size.setValue(1)
        fps_layout.addWidget(self.adv_buffer_size, 2, 1)

        self.adv_force_camera_fps = QCheckBox("Forzar FPS en la cámara (CAP_PROP_FPS)")
        fps_layout.addWidget(self.adv_force_camera_fps, 3, 0, 1, 2)

        layout.addWidget(fps_group)

        # ========== Throttle ==========
        throttle_group = QGroupBox("⚡ Throttle Adaptativo")
        throttle_layout = QGridLayout(throttle_group)
        throttle_layout.setVerticalSpacing(10)
        throttle_layout.setHorizontalSpacing(20)

        self.adv_throttle_enabled = QCheckBox("Activar throttle adaptativo")
        self.adv_throttle_enabled.setChecked(True)
        throttle_layout.addWidget(self.adv_throttle_enabled, 0, 0, 1, 2)

        throttle_layout.addWidget(QLabel("CPU objetivo:"), 1, 0)
        cpu_layout = QHBoxLayout()
        self.adv_throttle_target_cpu = QDoubleSpinBox()
        self.adv_throttle_target_cpu.setRange(0.1, 8.0)
        self.adv_throttle_target_cpu.setValue(1.5)
        self.adv_throttle_target_cpu.setSingleStep(0.1)
        self.adv_throttle_target_cpu.setDecimals(1)
        cpu_layout.addWidget(self.adv_throttle_target_cpu)
        cpu_layout.addWidget(QLabel("núcleos"))
        cpu_layout.addStretch()
        throttle_layout.addLayout(cpu_layout, 1, 1)

        throttle_layout.addWidget(QLabel("GPU objetivo:"), 2, 0)
        gpu_layout = QHBoxLayout()
        self.adv_throttle_target_gpu = QDoubleSpinBox()
        self.adv_throttle_target_gpu.setRange(0.1, 1.0)
        self.adv_throttle_target_gpu.setValue(0.80)
        self.adv_throttle_target_gpu.setSingleStep(0.05)
        self.adv_throttle_target_gpu.setDecimals(2)
        gpu_layout.addWidget(self.adv_throttle_target_gpu)
        gpu_layout.addStretch()
        throttle_layout.addLayout(gpu_layout, 2, 1)

        throttle_layout.addWidget(QLabel("Máx. skip:"), 3, 0)
        self.adv_throttle_max_skip = QSpinBox()
        self.adv_throttle_max_skip.setRange(0, 10)
        self.adv_throttle_max_skip.setValue(3)
        throttle_layout.addWidget(self.adv_throttle_max_skip, 3, 1)

        throttle_layout.addWidget(QLabel("Intervalo:"), 4, 0)
        self.adv_throttle_check_interval = QDoubleSpinBox()
        self.adv_throttle_check_interval.setRange(0.1, 10.0)
        self.adv_throttle_check_interval.setValue(1.0)
        self.adv_throttle_check_interval.setSingleStep(0.1)
        self.adv_throttle_check_interval.setSuffix(" s")
        throttle_layout.addWidget(self.adv_throttle_check_interval, 4, 1)

        throttle_layout.addWidget(QLabel("Histéresis:"), 5, 0)
        self.adv_throttle_hysteresis = QDoubleSpinBox()
        self.adv_throttle_hysteresis.setRange(0.05, 0.50)
        self.adv_throttle_hysteresis.setValue(0.30)
        self.adv_throttle_hysteresis.setSingleStep(0.05)
        self.adv_throttle_hysteresis.setDecimals(2)
        throttle_layout.addWidget(self.adv_throttle_hysteresis, 5, 1)

        throttle_layout.addWidget(QLabel("GPU sample:"), 6, 0)
        self.adv_throttle_gpu_measure_sample = QSpinBox()
        self.adv_throttle_gpu_measure_sample.setRange(1, 30)
        self.adv_throttle_gpu_measure_sample.setValue(5)
        throttle_layout.addWidget(self.adv_throttle_gpu_measure_sample, 6, 1)

        layout.addWidget(throttle_group)

        # ========== Detección General ==========
        det_group = QGroupBox("🔍 Detección General")
        det_layout = QGridLayout(det_group)

        det_layout.addWidget(QLabel("Saltar frames (detección):"), 0, 0)
        self.adv_detection_skip = QSpinBox()
        self.adv_detection_skip.setRange(1, 30)
        self.adv_detection_skip.setValue(3)
        det_layout.addWidget(self.adv_detection_skip, 0, 1)

        det_layout.addWidget(QLabel("Saltar frames (escaneo):"), 1, 0)
        self.adv_scan_skip = QSpinBox()
        self.adv_scan_skip.setRange(1, 60)
        self.adv_scan_skip.setValue(5)
        det_layout.addWidget(self.adv_scan_skip, 1, 1)

        layout.addWidget(det_group)

        # ========== Red ==========
        net_group = QGroupBox("🌐 Red")
        net_layout = QGridLayout(net_group)
        net_layout.setVerticalSpacing(10)
        net_layout.setHorizontalSpacing(20)

        net_layout.addWidget(QLabel("Timeout conexión:"), 0, 0)
        self.adv_conn_timeout = QDoubleSpinBox()
        self.adv_conn_timeout.setRange(0.5, 30.0)
        self.adv_conn_timeout.setValue(2.0)
        self.adv_conn_timeout.setSingleStep(0.5)
        self.adv_conn_timeout.setSuffix(" s")
        net_layout.addWidget(self.adv_conn_timeout, 0, 1)

        net_layout.addWidget(QLabel("Timeout lectura:"), 1, 0)
        self.adv_read_timeout = QDoubleSpinBox()
        self.adv_read_timeout.setRange(0.5, 30.0)
        self.adv_read_timeout.setValue(2.0)
        self.adv_read_timeout.setSingleStep(0.5)
        self.adv_read_timeout.setSuffix(" s")
        net_layout.addWidget(self.adv_read_timeout, 1, 1)

        net_layout.addWidget(QLabel("Retraso reconexión:"), 2, 0)
        self.adv_reconnect_delay = QDoubleSpinBox()
        self.adv_reconnect_delay.setRange(0.1, 10.0)
        self.adv_reconnect_delay.setValue(0.5)
        self.adv_reconnect_delay.setSingleStep(0.1)
        self.adv_reconnect_delay.setSuffix(" s")
        net_layout.addWidget(self.adv_reconnect_delay, 2, 1)

        net_layout.addWidget(QLabel("Intentos reconexión:"), 3, 0)
        self.adv_reconnect_attempts = QSpinBox()
        self.adv_reconnect_attempts.setRange(1, 20)
        self.adv_reconnect_attempts.setValue(3)
        net_layout.addWidget(self.adv_reconnect_attempts, 3, 1)

        net_layout.addWidget(QLabel("Timeout frame:"), 4, 0)
        self.adv_frame_timeout = QDoubleSpinBox()
        self.adv_frame_timeout.setRange(1.0, 60.0)
        self.adv_frame_timeout.setValue(5.0)
        self.adv_frame_timeout.setSingleStep(0.5)
        self.adv_frame_timeout.setSuffix(" s")
        net_layout.addWidget(self.adv_frame_timeout, 4, 1)

        layout.addWidget(net_group)

        # ========== Grabación ==========
        rec_group = QGroupBox("🎬 Grabación")
        rec_layout = QGridLayout(rec_group)
        rec_layout.setVerticalSpacing(10)
        rec_layout.setHorizontalSpacing(20)

        self.adv_record_audio = QCheckBox("Grabar con audio si está disponible")
        self.adv_record_audio.setChecked(True)
        rec_layout.addWidget(self.adv_record_audio, 0, 0, 1, 2)

        rec_layout.addWidget(QLabel("Backend:"), 1, 0)
        self.adv_av_recorder_backend = QComboBox()
        self.adv_av_recorder_backend.addItems(["auto", "opencv", "pyav"])
        rec_layout.addWidget(self.adv_av_recorder_backend, 1, 1)

        self.adv_auto_reencode_wrong_fps = QCheckBox("Auto-corregir FPS al terminar")
        rec_layout.addWidget(self.adv_auto_reencode_wrong_fps, 2, 0, 1, 2)

        rec_layout.addWidget(QLabel("Umbral re-encodeo:"), 3, 0)
        self.adv_auto_reencode_threshold = QDoubleSpinBox()
        self.adv_auto_reencode_threshold.setRange(1.0, 100.0)
        self.adv_auto_reencode_threshold.setValue(50.0)
        self.adv_auto_reencode_threshold.setSingleStep(5.0)
        self.adv_auto_reencode_threshold.setSuffix(" %")
        rec_layout.addWidget(self.adv_auto_reencode_threshold, 3, 1)

        rec_layout.addWidget(QLabel("Auto-detener después de:"), 4, 0)
        self.adv_record_auto_stop_after = QSpinBox()
        self.adv_record_auto_stop_after.setRange(0, 3600)
        self.adv_record_auto_stop_after.setValue(0)
        self.adv_record_auto_stop_after.setSuffix(" s")
        rec_layout.addWidget(self.adv_record_auto_stop_after, 4, 1)

        rec_layout.addWidget(QLabel("CRF (calidad H.264):"), 5, 0)
        self.adv_video_crf = QSpinBox()
        self.adv_video_crf.setRange(0, 51)
        self.adv_video_crf.setValue(23)
        rec_layout.addWidget(self.adv_video_crf, 5, 1)

        rec_layout.addWidget(QLabel("Preset H.264:"), 6, 0)
        self.adv_video_preset = QComboBox()
        self.adv_video_preset.addItems(["ultrafast", "superfast", "veryfast",
                                        "faster", "fast", "medium", "slow"])
        self.adv_video_preset.setCurrentText("fast")
        rec_layout.addWidget(self.adv_video_preset, 6, 1)

        rec_layout.addWidget(QLabel("Timeout re-encodeo:"), 9, 0)
        self.adv_reencode_timeout = QSpinBox()
        self.adv_reencode_timeout.setRange(10, 600)
        self.adv_reencode_timeout.setValue(120)
        self.adv_reencode_timeout.setSingleStep(10)
        self.adv_reencode_timeout.setSuffix(" s")
        rec_layout.addWidget(self.adv_reencode_timeout, 9, 1)

        layout.addWidget(rec_group)

        # ========== Sistema ==========
        sys_group = QGroupBox("🖥️ Sistema")
        sys_layout = QGridLayout(sys_group)
        sys_layout.setVerticalSpacing(10)
        sys_layout.setHorizontalSpacing(20)

        sys_layout.addWidget(QLabel("Intervalo monitor:"), 0, 0)
        self.adv_system_monitor_interval = QDoubleSpinBox()
        self.adv_system_monitor_interval.setRange(0.1, 10.0)
        self.adv_system_monitor_interval.setValue(1.0)
        self.adv_system_monitor_interval.setSingleStep(0.1)
        self.adv_system_monitor_interval.setSuffix(" s")
        sys_layout.addWidget(self.adv_system_monitor_interval, 0, 1)

        sys_layout.addWidget(QLabel("GPU index:"), 1, 0)
        self.adv_system_monitor_gpu_index = QSpinBox()
        self.adv_system_monitor_gpu_index.setRange(0, 7)
        self.adv_system_monitor_gpu_index.setValue(0)
        sys_layout.addWidget(self.adv_system_monitor_gpu_index, 1, 1)

        sys_layout.addWidget(QLabel("Workers miniaturas:"), 2, 0)
        self.adv_video_thumbnail_workers = QSpinBox()
        self.adv_video_thumbnail_workers.setRange(1, 8)
        self.adv_video_thumbnail_workers.setValue(2)
        sys_layout.addWidget(self.adv_video_thumbnail_workers, 2, 1)

        sys_layout.addWidget(QLabel("Tamaño miniatura:"), 3, 0)
        self.adv_video_thumbnail_size = QSpinBox()
        self.adv_video_thumbnail_size.setRange(60, 400)
        self.adv_video_thumbnail_size.setValue(160)
        self.adv_video_thumbnail_size.setSuffix(" px")
        sys_layout.addWidget(self.adv_video_thumbnail_size, 3, 1)

        self.adv_thumbnail_cache_enabled = QCheckBox("Cachear miniaturas")
        self.adv_thumbnail_cache_enabled.setChecked(True)
        sys_layout.addWidget(self.adv_thumbnail_cache_enabled, 4, 0, 1, 2)

        sys_layout.addWidget(QLabel("Máx. cámaras locales:"), 5, 0)
        self.adv_local_max_devices_detect = QSpinBox()
        self.adv_local_max_devices_detect.setRange(1, 20)
        self.adv_local_max_devices_detect.setValue(5)
        sys_layout.addWidget(self.adv_local_max_devices_detect, 5, 1)

        layout.addWidget(sys_group)

        # ========== Video Preview ==========
        vp_group = QGroupBox("🎥 Visor de Video")
        vp_layout = QGridLayout(vp_group)
        vp_layout.setVerticalSpacing(10)
        vp_layout.setHorizontalSpacing(20)

        vp_layout.addWidget(QLabel("Posición miniatura:"), 0, 0)
        self.adv_thumbnail_frame_position = QDoubleSpinBox()
        self.adv_thumbnail_frame_position.setRange(0.0, 1.0)
        self.adv_thumbnail_frame_position.setValue(0.25)
        self.adv_thumbnail_frame_position.setSingleStep(0.05)
        self.adv_thumbnail_frame_position.setDecimals(2)
        vp_layout.addWidget(self.adv_thumbnail_frame_position, 0, 1)

        vp_layout.addWidget(QLabel("Volumen inicial:"), 1, 0)
        self.adv_video_default_volume = QDoubleSpinBox()
        self.adv_video_default_volume.setRange(0.0, 1.0)
        self.adv_video_default_volume.setValue(0.7)
        self.adv_video_default_volume.setSingleStep(0.05)
        self.adv_video_default_volume.setDecimals(2)
        vp_layout.addWidget(self.adv_video_default_volume, 1, 1)

        vp_layout.addWidget(QLabel("Salto pequeño:"), 2, 0)
        self.adv_seek_step_small = QSpinBox()
        self.adv_seek_step_small.setRange(1, 30)
        self.adv_seek_step_small.setValue(5)
        self.adv_seek_step_small.setSuffix(" s")
        vp_layout.addWidget(self.adv_seek_step_small, 2, 1)

        vp_layout.addWidget(QLabel("Salto grande:"), 3, 0)
        self.adv_seek_step_big = QSpinBox()
        self.adv_seek_step_big.setRange(10, 120)
        self.adv_seek_step_big.setValue(30)
        self.adv_seek_step_big.setSingleStep(10)
        self.adv_seek_step_big.setSuffix(" s")
        vp_layout.addWidget(self.adv_seek_step_big, 3, 1)

        vp_layout.addWidget(QLabel("Salto frame a frame:"), 4, 0)
        self.adv_step_frame_ms = QSpinBox()
        self.adv_step_frame_ms.setRange(16, 200)
        self.adv_step_frame_ms.setValue(33)
        self.adv_step_frame_ms.setSuffix(" ms")
        vp_layout.addWidget(self.adv_step_frame_ms, 4, 1)

        layout.addWidget(vp_group)

        # ========== UI ==========
        ui_group = QGroupBox("🎨 UI")
        ui_layout = QGridLayout(ui_group)
        ui_layout.setVerticalSpacing(10)
        ui_layout.setHorizontalSpacing(20)

        ui_layout.addWidget(QLabel("Tamaño mín. widget:"), 0, 0)
        size_min = QHBoxLayout()
        self.adv_camera_widget_min_width = QSpinBox()
        self.adv_camera_widget_min_width.setRange(200, 1000)
        self.adv_camera_widget_min_width.setValue(320)
        self.adv_camera_widget_min_width.setSuffix(" px")
        size_min.addWidget(self.adv_camera_widget_min_width)
        size_min.addWidget(QLabel("x"))
        self.adv_camera_widget_min_height = QSpinBox()
        self.adv_camera_widget_min_height.setRange(150, 800)
        self.adv_camera_widget_min_height.setValue(280)
        self.adv_camera_widget_min_height.setSuffix(" px")
        size_min.addWidget(self.adv_camera_widget_min_height)
        size_min.addStretch()
        ui_layout.addLayout(size_min, 0, 1)

        ui_layout.addWidget(QLabel("Tamaño máx. widget:"), 1, 0)
        size_max = QHBoxLayout()
        self.adv_camera_widget_max_width = QSpinBox()
        self.adv_camera_widget_max_width.setRange(300, 2000)
        self.adv_camera_widget_max_width.setValue(480)
        self.adv_camera_widget_max_width.setSuffix(" px")
        size_max.addWidget(self.adv_camera_widget_max_width)
        size_max.addWidget(QLabel("x"))
        self.adv_camera_widget_max_height = QSpinBox()
        self.adv_camera_widget_max_height.setRange(200, 1500)
        self.adv_camera_widget_max_height.setValue(400)
        self.adv_camera_widget_max_height.setSuffix(" px")
        size_max.addWidget(self.adv_camera_widget_max_height)
        size_max.addStretch()
        ui_layout.addLayout(size_max, 1, 1)

        ui_layout.addWidget(QLabel("Timeout overlay:"), 2, 0)
        self.adv_loading_overlay_timeout = QSpinBox()
        self.adv_loading_overlay_timeout.setRange(100, 5000)
        self.adv_loading_overlay_timeout.setValue(500)
        self.adv_loading_overlay_timeout.setSingleStep(100)
        self.adv_loading_overlay_timeout.setSuffix(" ms")
        ui_layout.addWidget(self.adv_loading_overlay_timeout, 2, 1)

        ui_layout.addWidget(QLabel("FPS repintado widget:"), 3, 0)
        self.adv_camera_display_fps = QSpinBox()
        self.adv_camera_display_fps.setRange(5, 60)
        self.adv_camera_display_fps.setValue(30)
        self.adv_camera_display_fps.setSuffix(" FPS")
        ui_layout.addWidget(self.adv_camera_display_fps, 3, 1)

        ui_layout.addWidget(QLabel("FPS check interval:"), 4, 0)
        self.adv_camera_fps_check_interval = QSpinBox()
        self.adv_camera_fps_check_interval.setRange(100, 5000)
        self.adv_camera_fps_check_interval.setValue(1000)
        self.adv_camera_fps_check_interval.setSingleStep(100)
        self.adv_camera_fps_check_interval.setSuffix(" ms")
        ui_layout.addWidget(self.adv_camera_fps_check_interval, 4, 1)

        ui_layout.addWidget(QLabel("Recording update interval:"), 5, 0)
        self.adv_recording_update_interval = QSpinBox()
        self.adv_recording_update_interval.setRange(100, 5000)
        self.adv_recording_update_interval.setValue(1000)
        self.adv_recording_update_interval.setSingleStep(100)
        self.adv_recording_update_interval.setSuffix(" ms")
        ui_layout.addWidget(self.adv_recording_update_interval, 5, 1)

        ui_layout.addWidget(QLabel("Buffers QPixmap:"), 6, 0)
        self.adv_pixmap_pool_size = QSpinBox()
        self.adv_pixmap_pool_size.setRange(2, 10)
        self.adv_pixmap_pool_size.setValue(3)
        ui_layout.addWidget(self.adv_pixmap_pool_size, 6, 1)

        ui_layout.addWidget(QLabel("Duración animación:"), 7, 0)
        self.adv_anim_duration_ms = QSpinBox()
        self.adv_anim_duration_ms.setRange(100, 1000)
        self.adv_anim_duration_ms.setValue(350)
        self.adv_anim_duration_ms.setSingleStep(50)
        self.adv_anim_duration_ms.setSuffix(" ms")
        ui_layout.addWidget(self.adv_anim_duration_ms, 7, 1)

        ui_layout.addWidget(QLabel("Espacio del grid:"), 8, 0)
        self.adv_grid_spacing = QSpinBox()
        self.adv_grid_spacing.setRange(4, 30)
        self.adv_grid_spacing.setValue(12)
        self.adv_grid_spacing.setSuffix(" px")
        ui_layout.addWidget(self.adv_grid_spacing, 8, 1)

        ui_layout.addWidget(QLabel("Margen del grid:"), 9, 0)
        self.adv_grid_margins = QSpinBox()
        self.adv_grid_margins.setRange(0, 40)
        self.adv_grid_margins.setValue(8)
        self.adv_grid_margins.setSuffix(" px")
        ui_layout.addWidget(self.adv_grid_margins, 9, 1)

        ui_layout.addWidget(QLabel("Intervalo VU meter:"), 10, 0)
        self.adv_audio_meter_interval = QSpinBox()
        self.adv_audio_meter_interval.setRange(20, 200)
        self.adv_audio_meter_interval.setValue(50)
        self.adv_audio_meter_interval.setSingleStep(10)
        self.adv_audio_meter_interval.setSuffix(" ms")
        ui_layout.addWidget(self.adv_audio_meter_interval, 10, 1)

        layout.addWidget(ui_group)

        # ========== Main Window ==========
        main_group = QGroupBox("🪟 Ventana Principal")
        main_glayout = QGridLayout(main_group)
        main_glayout.setVerticalSpacing(10)
        main_glayout.setHorizontalSpacing(20)

        main_glayout.addWidget(QLabel("Intervalo auto-captura:"), 0, 0)
        self.adv_auto_capture_interval = QSpinBox()
        self.adv_auto_capture_interval.setRange(1000, 60000)
        self.adv_auto_capture_interval.setValue(5000)
        self.adv_auto_capture_interval.setSingleStep(1000)
        self.adv_auto_capture_interval.setSuffix(" ms")
        main_glayout.addWidget(self.adv_auto_capture_interval, 0, 1)

        main_glayout.addWidget(QLabel("Flash ON (ms):"), 1, 0)
        self.adv_flash_on_duration_ms = QSpinBox()
        self.adv_flash_on_duration_ms.setRange(500, 10000)
        self.adv_flash_on_duration_ms.setValue(2000)
        self.adv_flash_on_duration_ms.setSingleStep(500)
        self.adv_flash_on_duration_ms.setSuffix(" ms")
        main_glayout.addWidget(self.adv_flash_on_duration_ms, 1, 1)

        main_glayout.addWidget(QLabel("Flash OFF después de:"), 2, 0)
        self.adv_flash_off_duration_ms = QSpinBox()
        self.adv_flash_off_duration_ms.setRange(500, 10000)
        self.adv_flash_off_duration_ms.setValue(1000)
        self.adv_flash_off_duration_ms.setSingleStep(500)
        self.adv_flash_off_duration_ms.setSuffix(" ms")
        main_glayout.addWidget(self.adv_flash_off_duration_ms, 2, 1)

        main_glayout.addWidget(QLabel("Delay carga cámaras:"), 3, 0)
        self.adv_loading_timeout = QSpinBox()
        self.adv_loading_timeout.setRange(0, 5000)
        self.adv_loading_timeout.setValue(500)
        self.adv_loading_timeout.setSingleStep(100)
        self.adv_loading_timeout.setSuffix(" ms")
        main_glayout.addWidget(self.adv_loading_timeout, 3, 1)

        layout.addWidget(main_group)

        # ========== File Manager ==========
        fm_group = QGroupBox("📁 File Manager")
        fm_layout = QGridLayout(fm_group)
        fm_layout.setVerticalSpacing(10)
        fm_layout.setHorizontalSpacing(20)

        fm_layout.addWidget(QLabel("Interpolación imágenes:"), 0, 0)
        self.adv_image_interpolation = QComboBox()
        self.adv_image_interpolation.addItems(["linear", "nearest", "cubic", "area", "lanczos4"])
        self.adv_image_interpolation.setCurrentText("linear")
        fm_layout.addWidget(self.adv_image_interpolation, 0, 1)

        fm_layout.addWidget(QLabel("Interpolación videos:"), 1, 0)
        self.adv_video_interpolation = QComboBox()
        self.adv_video_interpolation.addItems(["linear", "nearest", "cubic", "area", "lanczos4"])
        self.adv_video_interpolation.setCurrentText("linear")
        fm_layout.addWidget(self.adv_video_interpolation, 1, 1)

        layout.addWidget(fm_group)

        # ========== Splash / Loading ==========
        splash_group = QGroupBox("⏳ Splash y Loading Overlay")
        splash_layout = QGridLayout(splash_group)
        splash_layout.setVerticalSpacing(10)
        splash_layout.setHorizontalSpacing(20)

        splash_layout.addWidget(QLabel("Dots interval:"), 0, 0)
        self.adv_loading_dots_interval = QSpinBox()
        self.adv_loading_dots_interval.setRange(100, 2000)
        self.adv_loading_dots_interval.setValue(400)
        self.adv_loading_dots_interval.setSuffix(" ms")
        splash_layout.addWidget(self.adv_loading_dots_interval, 0, 1)

        splash_layout.addWidget(QLabel("Spinner interval:"), 1, 0)
        self.adv_loading_spinner_interval = QSpinBox()
        self.adv_loading_spinner_interval.setRange(100, 2000)
        self.adv_loading_spinner_interval.setValue(500)
        self.adv_loading_spinner_interval.setSuffix(" ms")
        splash_layout.addWidget(self.adv_loading_spinner_interval, 1, 1)

        splash_layout.addWidget(QLabel("Fade overlay:"), 2, 0)
        self.adv_loading_fade_duration = QSpinBox()
        self.adv_loading_fade_duration.setRange(50, 1000)
        self.adv_loading_fade_duration.setValue(200)
        self.adv_loading_fade_duration.setSuffix(" ms")
        splash_layout.addWidget(self.adv_loading_fade_duration, 2, 1)

        splash_layout.addWidget(QLabel("Fade in splash:"), 3, 0)
        self.adv_splash_fade_in_duration = QSpinBox()
        self.adv_splash_fade_in_duration.setRange(100, 2000)
        self.adv_splash_fade_in_duration.setValue(400)
        self.adv_splash_fade_in_duration.setSuffix(" ms")
        splash_layout.addWidget(self.adv_splash_fade_in_duration, 3, 1)

        splash_layout.addWidget(QLabel("Fade out splash:"), 4, 0)
        self.adv_splash_fade_out_duration = QSpinBox()
        self.adv_splash_fade_out_duration.setRange(100, 2000)
        self.adv_splash_fade_out_duration.setValue(300)
        self.adv_splash_fade_out_duration.setSuffix(" ms")
        splash_layout.addWidget(self.adv_splash_fade_out_duration, 4, 1)

        layout.addWidget(splash_group)

        # ========== Hardware ==========
        hw_group = QGroupBox("💻 Hardware")
        hw_layout = QVBoxLayout(hw_group)
        self.adv_gpu = QCheckBox("Usar aceleración por GPU (si está disponible)")
        hw_layout.addWidget(self.adv_gpu)
        layout.addWidget(hw_group)

        # ========== Inicio ==========
        startup_group = QGroupBox("🚀 Inicio")
        startup_layout = QVBoxLayout(startup_group)
        self.adv_auto_start = QCheckBox("Iniciar ProCamera con Windows")
        startup_layout.addWidget(self.adv_auto_start)
        self.adv_remember_state = QCheckBox("Recordar estado al cerrar")
        self.adv_remember_state.setChecked(True)
        startup_layout.addWidget(self.adv_remember_state)
        layout.addWidget(startup_group)

        layout.addStretch()
        scroll.setWidget(content)
        main_layout.addWidget(scroll)

        # Guardamos la referencia al scroll para recargarlo al final
        self._system_scroll = scroll
        return widget

    # ==================== PESTAÑA DEBUG ====================

    def _create_debug_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        debug_group = QGroupBox("🐛 Depuración")
        debug_layout = QGridLayout(debug_group)
        debug_layout.setVerticalSpacing(10)
        debug_layout.setHorizontalSpacing(20)

        self.adv_debug = QCheckBox("Modo depuración")
        debug_layout.addWidget(self.adv_debug, 0, 0, 1, 2)

        self.adv_save_logs = QCheckBox("Guardar logs en archivo")
        self.adv_save_logs.setChecked(True)
        debug_layout.addWidget(self.adv_save_logs, 1, 0, 1, 2)

        debug_layout.addWidget(QLabel("Nivel de logs:"), 2, 0)
        self.adv_log_level = QComboBox()
        self.adv_log_level.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        self.adv_log_level.setCurrentText("INFO")
        debug_layout.addWidget(self.adv_log_level, 2, 1)

        clear_cache_btn = QPushButton("🗑️ Limpiar caché y temporales")
        clear_cache_btn.clicked.connect(self._clear_cache)
        debug_layout.addWidget(clear_cache_btn, 3, 0, 1, 2)

        layout.addWidget(debug_group)

        reset_btn = QPushButton("🔄 Restaurar valores por defecto")
        reset_btn.clicked.connect(self._reset_advanced)
        layout.addWidget(reset_btn)

        layout.addStretch()
        return widget

    # ==================== UTILIDADES ====================

    def _clear_cache(self):
        reply = QMessageBox.question(
            self, "Confirmar",
            "¿Limpiar caché y archivos temporales?\n\nNo se eliminarán capturas ni configuración.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        try:
            import tempfile
            import shutil
            temp_dir = tempfile.gettempdir()
            cleared = 0
            for filename in os.listdir(temp_dir):
                if filename.startswith('procamara_'):
                    file_path = os.path.join(temp_dir, filename)
                    try:
                        if os.path.isfile(file_path):
                            os.unlink(file_path)
                            cleared += 1
                        elif os.path.isdir(file_path):
                            shutil.rmtree(file_path)
                            cleared += 1
                    except Exception:
                        pass
            cache_path = "known_faces/.cache.pkl"
            if os.path.exists(cache_path):
                os.remove(cache_path)
                cleared += 1
            QMessageBox.information(self, "Éxito",
                                     f"✅ Caché limpiada\n{cleared} archivos eliminados")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Error: {e}")

    def _reset_advanced(self):
        reply = QMessageBox.question(self, "Confirmar",
                                     "¿Restaurar valores por defecto?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        d = AdvancedConfig.DEFAULTS

        # FPS
        self.adv_target_fps.setValue(d["target_fps"])
        self.adv_screen_max_fps.setValue(d["screen_max_fps"])
        self.adv_buffer_size.setValue(d["buffer_size"])
        self.adv_force_camera_fps.setChecked(d["force_camera_fps"])

        # Throttle
        self.adv_throttle_enabled.setChecked(d["throttle_enabled"])
        self.adv_throttle_target_cpu.setValue(d["throttle_target_cpu"])
        self.adv_throttle_target_gpu.setValue(d["throttle_target_gpu"])
        self.adv_throttle_max_skip.setValue(d["throttle_max_skip"])
        self.adv_throttle_check_interval.setValue(d["throttle_check_interval"])
        self.adv_throttle_hysteresis.setValue(d["throttle_hysteresis"])
        self.adv_throttle_gpu_measure_sample.setValue(d["throttle_gpu_measure_sample"])

        # Detección
        self.adv_detection_skip.setValue(d["detection_frame_skip"])
        self.adv_scan_skip.setValue(d["scan_frame_skip"])

        # Grabación
        self.adv_record_audio.setChecked(d["record_audio"])
        self.adv_av_recorder_backend.setCurrentText(d["av_recorder_backend"])
        self.adv_auto_reencode_wrong_fps.setChecked(d["auto_reencode_wrong_fps"])
        self.adv_auto_reencode_threshold.setValue(d["auto_reencode_threshold"])
        self.adv_record_auto_stop_after.setValue(d["record_auto_stop_after"])
        self.adv_video_crf.setValue(d["video_crf"])
        self.adv_video_preset.setCurrentText(d["video_preset"])
        self.adv_reencode_timeout.setValue(d["reencode_timeout"])

        # Red
        self.adv_conn_timeout.setValue(d["connection_timeout"])
        self.adv_read_timeout.setValue(d["read_timeout"])
        self.adv_reconnect_delay.setValue(d["reconnect_delay"])
        self.adv_reconnect_attempts.setValue(d["reconnect_attempts"])
        self.adv_frame_timeout.setValue(d["frame_timeout"])

        # Sistema
        self.adv_system_monitor_interval.setValue(d["system_monitor_interval"])
        self.adv_system_monitor_gpu_index.setValue(d["system_monitor_gpu_index"])
        self.adv_video_thumbnail_workers.setValue(d["video_thumbnail_workers"])
        self.adv_video_thumbnail_size.setValue(d["video_thumbnail_size"])
        self.adv_thumbnail_cache_enabled.setChecked(d["thumbnail_cache_enabled"])
        self.adv_local_max_devices_detect.setValue(d["local_max_devices_detect"])

        # UI
        self.adv_camera_widget_min_width.setValue(d["camera_widget_min_width"])
        self.adv_camera_widget_min_height.setValue(d["camera_widget_min_height"])
        self.adv_camera_widget_max_width.setValue(d["camera_widget_max_width"])
        self.adv_camera_widget_max_height.setValue(d["camera_widget_max_height"])
        self.adv_loading_overlay_timeout.setValue(d["loading_overlay_timeout"])
        self.adv_camera_display_fps.setValue(d["camera_display_fps"])
        self.adv_camera_fps_check_interval.setValue(d["camera_fps_check_interval"])
        self.adv_recording_update_interval.setValue(d["recording_update_interval"])
        self.adv_pixmap_pool_size.setValue(d["pixmap_pool_size"])
        self.adv_anim_duration_ms.setValue(d["anim_duration_ms"])
        self.adv_grid_spacing.setValue(d["grid_spacing"])
        self.adv_grid_margins.setValue(d["grid_margins"])
        self.adv_audio_meter_interval.setValue(d["audio_meter_interval"])

        # Video Preview
        self.adv_thumbnail_frame_position.setValue(d["thumbnail_frame_position"])
        self.adv_video_default_volume.setValue(d["video_default_volume"])
        self.adv_seek_step_small.setValue(d["seek_step_small"])
        self.adv_seek_step_big.setValue(d["seek_step_big"])
        self.adv_step_frame_ms.setValue(d["step_frame_ms"])

        # Main Window
        self.adv_auto_capture_interval.setValue(d["auto_capture_interval"])
        self.adv_flash_on_duration_ms.setValue(d["flash_on_duration_ms"])
        self.adv_flash_off_duration_ms.setValue(d["flash_off_duration_ms"])
        self.adv_loading_timeout.setValue(d["loading_timeout"])

        # File Manager
        self.adv_image_interpolation.setCurrentText(d["image_interpolation"])
        self.adv_video_interpolation.setCurrentText(d["video_interpolation"])

        # Splash / Loading
        self.adv_loading_dots_interval.setValue(d["loading_dots_interval"])
        self.adv_loading_spinner_interval.setValue(d["loading_spinner_interval"])
        self.adv_loading_fade_duration.setValue(d["loading_fade_duration"])
        self.adv_splash_fade_in_duration.setValue(d["splash_fade_in_duration"])
        self.adv_splash_fade_out_duration.setValue(d["splash_fade_out_duration"])

        # Hardware / Inicio / Debug
        self.adv_gpu.setChecked(d["gpu_acceleration"])
        self.adv_auto_start.setChecked(d["auto_start"])
        self.adv_remember_state.setChecked(d["remember_last_state"])
        self.adv_debug.setChecked(d["debug_mode"])
        self.adv_save_logs.setChecked(d["save_logs"])
        self.adv_log_level.setCurrentText(d["log_level"])

        QMessageBox.information(self, "Éxito", "✅ Valores restaurados")

    # ==================== CARGA ====================

    def _load_settings(self):
        """Carga tabs core."""
        import time
        t0 = time.perf_counter()
        logger.debug("🔵 [_load_settings] Cargando pestañas básicas...")

        self._update_camera_list(settings_manager.get_cameras())

        # Captura
        cs = settings_manager.get_capture_settings()
        self.img_format.setCurrentText(cs.image_format.value.upper())
        self.img_resolution.setCurrentText(cs.image_resolution.display_name)
        self.img_quality_slider.setValue(cs.image_quality)
        self.vid_format.setCurrentText(cs.video_format.value.upper())
        self.vid_resolution.setCurrentText(cs.video_resolution.display_name)
        self.vid_fps.setValue(cs.video_fps)
        self.vid_quality_slider.setValue(cs.video_quality)
        self.default_name.setText(cs.default_name)
        self.default_dir.setText(cs.default_directory)

        # UI
        ui = settings_manager.get_ui_settings()
        self.theme_combo.setCurrentText(ui.get("theme", "dark").capitalize())
        self.grid_columns.setValue(ui.get("camera_grid_columns", 2))

        self._update_codecs(self.vid_format.currentText())

        # ✅ Sistema (incluye los params que estaban en Avanzado)
        self._load_system_settings()

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.debug(f"🔵 [_load_settings] OK en {elapsed_ms:.0f}ms")

    def _load_system_settings(self):
        """Carga los parámetros de la tab Sistema + Debug."""
        adv = settings_manager.get_advanced_settings()

        # FPS
        self.adv_target_fps.setValue(adv.get("target_fps", 30))
        self.adv_screen_max_fps.setValue(adv.get("screen_max_fps", 30))
        self.adv_buffer_size.setValue(adv.get("buffer_size", 1))
        self.adv_force_camera_fps.setChecked(adv.get("force_camera_fps", False))

        # Throttle
        self.adv_throttle_enabled.setChecked(adv.get("throttle_enabled", True))
        self.adv_throttle_target_cpu.setValue(adv.get("throttle_target_cpu", 1.5))
        self.adv_throttle_target_gpu.setValue(adv.get("throttle_target_gpu", 0.80))
        self.adv_throttle_max_skip.setValue(adv.get("throttle_max_skip", 3))
        self.adv_throttle_check_interval.setValue(adv.get("throttle_check_interval", 1.0))
        self.adv_throttle_hysteresis.setValue(adv.get("throttle_hysteresis", 0.30))
        self.adv_throttle_gpu_measure_sample.setValue(adv.get("throttle_gpu_measure_sample", 5))

        # Detección general
        self.adv_detection_skip.setValue(adv.get("detection_frame_skip", 3))
        self.adv_scan_skip.setValue(adv.get("scan_frame_skip", 5))

        # Red
        self.adv_conn_timeout.setValue(adv.get("connection_timeout", 2.0))
        self.adv_read_timeout.setValue(adv.get("read_timeout", 2.0))
        self.adv_reconnect_delay.setValue(adv.get("reconnect_delay", 0.5))
        self.adv_reconnect_attempts.setValue(adv.get("reconnect_attempts", 3))
        self.adv_frame_timeout.setValue(adv.get("frame_timeout", 5.0))

        # Grabación
        self.adv_record_audio.setChecked(adv.get("record_audio", True))
        self.adv_av_recorder_backend.setCurrentText(adv.get("av_recorder_backend", "auto"))
        self.adv_auto_reencode_wrong_fps.setChecked(adv.get("auto_reencode_wrong_fps", False))
        self.adv_auto_reencode_threshold.setValue(adv.get("auto_reencode_threshold", 50.0))
        self.adv_record_auto_stop_after.setValue(adv.get("record_auto_stop_after", 0))
        self.adv_video_crf.setValue(adv.get("video_crf", 23))
        self.adv_video_preset.setCurrentText(adv.get("video_preset", "fast"))
        self.adv_reencode_timeout.setValue(adv.get("reencode_timeout", 120))

        # Sistema
        self.adv_system_monitor_interval.setValue(adv.get("system_monitor_interval", 1.0))
        self.adv_system_monitor_gpu_index.setValue(adv.get("system_monitor_gpu_index", 0))
        self.adv_video_thumbnail_workers.setValue(adv.get("video_thumbnail_workers", 2))
        self.adv_video_thumbnail_size.setValue(adv.get("video_thumbnail_size", 160))
        self.adv_thumbnail_cache_enabled.setChecked(adv.get("thumbnail_cache_enabled", True))
        self.adv_local_max_devices_detect.setValue(adv.get("local_max_devices_detect", 5))

        # UI
        self.adv_camera_widget_min_width.setValue(adv.get("camera_widget_min_width", 320))
        self.adv_camera_widget_min_height.setValue(adv.get("camera_widget_min_height", 280))
        self.adv_camera_widget_max_width.setValue(adv.get("camera_widget_max_width", 480))
        self.adv_camera_widget_max_height.setValue(adv.get("camera_widget_max_height", 400))
        self.adv_loading_overlay_timeout.setValue(adv.get("loading_overlay_timeout", 500))
        self.adv_camera_display_fps.setValue(adv.get("camera_display_fps", 30))
        self.adv_camera_fps_check_interval.setValue(adv.get("camera_fps_check_interval", 1000))
        self.adv_recording_update_interval.setValue(adv.get("recording_update_interval", 1000))
        self.adv_pixmap_pool_size.setValue(adv.get("pixmap_pool_size", 3))
        self.adv_anim_duration_ms.setValue(adv.get("anim_duration_ms", 350))
        self.adv_grid_spacing.setValue(adv.get("grid_spacing", 12))
        self.adv_grid_margins.setValue(adv.get("grid_margins", 8))
        self.adv_audio_meter_interval.setValue(adv.get("audio_meter_interval", 50))

        # Video Preview
        self.adv_thumbnail_frame_position.setValue(adv.get("thumbnail_frame_position", 0.25))
        self.adv_video_default_volume.setValue(adv.get("video_default_volume", 0.7))
        self.adv_seek_step_small.setValue(adv.get("seek_step_small", 5))
        self.adv_seek_step_big.setValue(adv.get("seek_step_big", 30))
        self.adv_step_frame_ms.setValue(adv.get("step_frame_ms", 33))

        # Main Window
        self.adv_auto_capture_interval.setValue(adv.get("auto_capture_interval", 5000))
        self.adv_flash_on_duration_ms.setValue(adv.get("flash_on_duration_ms", 2000))
        self.adv_flash_off_duration_ms.setValue(adv.get("flash_off_duration_ms", 1000))
        self.adv_loading_timeout.setValue(adv.get("loading_timeout", 500))

        # File Manager
        self.adv_image_interpolation.setCurrentText(adv.get("image_interpolation", "linear"))
        self.adv_video_interpolation.setCurrentText(adv.get("video_interpolation", "linear"))

        # Splash / Loading
        self.adv_loading_dots_interval.setValue(adv.get("loading_dots_interval", 400))
        self.adv_loading_spinner_interval.setValue(adv.get("loading_spinner_interval", 500))
        self.adv_loading_fade_duration.setValue(adv.get("loading_fade_duration", 200))
        self.adv_splash_fade_in_duration.setValue(adv.get("splash_fade_in_duration", 400))
        self.adv_splash_fade_out_duration.setValue(adv.get("splash_fade_out_duration", 300))

        # Hardware / Inicio / Debug
        self.adv_gpu.setChecked(adv.get("gpu_acceleration", False))
        self.adv_auto_start.setChecked(adv.get("auto_start", False))
        self.adv_remember_state.setChecked(adv.get("remember_last_state", True))
        self.adv_debug.setChecked(adv.get("debug_mode", False))
        self.adv_save_logs.setChecked(adv.get("save_logs", True))
        self.adv_log_level.setCurrentText(adv.get("log_level", "INFO"))

    # ==================== GUARDADO ====================

    def _save_settings(self):
        """Guarda core + plugins."""
        import time
        from core.settings_manager import settings_manager
        t0 = time.perf_counter()

        logger.info("💾 [save] Iniciando guardado de settings")
        from utils.change_detector import ChangeDetector

        old_advanced = settings_manager.get_advanced_settings()
        old_capture = settings_manager.get_capture_settings()

        def get_resolution(name: str) -> Resolution:
            for r in Resolution:
                if r.display_name == name:
                    return r
            return Resolution.VGA

        # === CAPTURA ===
        cs = CaptureSettings(
            default_name=self.default_name.text(),
            default_directory=self.default_dir.text(),
            image_resolution=get_resolution(self.img_resolution.currentText()),
            video_resolution=get_resolution(self.vid_resolution.currentText()),
            image_format=ImageFormat(self.img_format.currentText().lower()),
            video_format=VideoFormat(self.vid_format.currentText().lower()),
            image_quality=self.img_quality_slider.value(),
            video_quality=self.vid_quality_slider.value(),
            video_fps=self.vid_fps.value(),
            video_codec=self.vid_codec.currentText()
        )
        settings_manager.save_capture_settings(cs)

        # === UI ===
        settings_manager.save_ui_settings({
            "theme": self.theme_combo.currentText().lower(),
            "camera_grid_columns": self.grid_columns.value()
        })

        # === AVANZADO (core + sistema, SIN motion/face/audio/notif) ===
        new_advanced = dict(old_advanced)  # mantener motion/face/audio/notif
        new_advanced.update({
            # FPS
            "target_fps": self.adv_target_fps.value(),
            "screen_max_fps": self.adv_screen_max_fps.value(),
            "buffer_size": self.adv_buffer_size.value(),
            "force_camera_fps": self.adv_force_camera_fps.isChecked(),
            # Throttle
            "throttle_enabled": self.adv_throttle_enabled.isChecked(),
            "throttle_target_cpu": self.adv_throttle_target_cpu.value(),
            "throttle_target_gpu": self.adv_throttle_target_gpu.value(),
            "throttle_max_skip": self.adv_throttle_max_skip.value(),
            "throttle_check_interval": self.adv_throttle_check_interval.value(),
            "throttle_hysteresis": self.adv_throttle_hysteresis.value(),
            "throttle_gpu_measure_sample": self.adv_throttle_gpu_measure_sample.value(),
            # Detección general
            "detection_frame_skip": self.adv_detection_skip.value(),
            "scan_frame_skip": self.adv_scan_skip.value(),
            # Grabación
            "record_audio": self.adv_record_audio.isChecked(),
            "av_recorder_backend": self.adv_av_recorder_backend.currentText(),
            "auto_reencode_wrong_fps": self.adv_auto_reencode_wrong_fps.isChecked(),
            "auto_reencode_threshold": self.adv_auto_reencode_threshold.value(),
            "record_auto_stop_after": self.adv_record_auto_stop_after.value(),
            "video_crf": self.adv_video_crf.value(),
            "video_preset": self.adv_video_preset.currentText(),
            "reencode_timeout": self.adv_reencode_timeout.value(),
            # Red
            "connection_timeout": self.adv_conn_timeout.value(),
            "read_timeout": self.adv_read_timeout.value(),
            "reconnect_delay": self.adv_reconnect_delay.value(),
            "reconnect_attempts": self.adv_reconnect_attempts.value(),
            "frame_timeout": self.adv_frame_timeout.value(),
            # Sistema
            "system_monitor_interval": self.adv_system_monitor_interval.value(),
            "system_monitor_gpu_index": self.adv_system_monitor_gpu_index.value(),
            "video_thumbnail_workers": self.adv_video_thumbnail_workers.value(),
            "video_thumbnail_size": self.adv_video_thumbnail_size.value(),
            "thumbnail_cache_enabled": self.adv_thumbnail_cache_enabled.isChecked(),
            "local_max_devices_detect": self.adv_local_max_devices_detect.value(),
            # UI
            "camera_widget_min_width": self.adv_camera_widget_min_width.value(),
            "camera_widget_min_height": self.adv_camera_widget_min_height.value(),
            "camera_widget_max_width": self.adv_camera_widget_max_width.value(),
            "camera_widget_max_height": self.adv_camera_widget_max_height.value(),
            "loading_overlay_timeout": self.adv_loading_overlay_timeout.value(),
            "camera_display_fps": self.adv_camera_display_fps.value(),
            "camera_fps_check_interval": self.adv_camera_fps_check_interval.value(),
            "recording_update_interval": self.adv_recording_update_interval.value(),
            "pixmap_pool_size": self.adv_pixmap_pool_size.value(),
            "anim_duration_ms": self.adv_anim_duration_ms.value(),
            "grid_spacing": self.adv_grid_spacing.value(),
            "grid_margins": self.adv_grid_margins.value(),
            "audio_meter_interval": self.adv_audio_meter_interval.value(),
            # Video Preview
            "thumbnail_frame_position": self.adv_thumbnail_frame_position.value(),
            "video_default_volume": self.adv_video_default_volume.value(),
            "seek_step_small": self.adv_seek_step_small.value(),
            "seek_step_big": self.adv_seek_step_big.value(),
            "step_frame_ms": self.adv_step_frame_ms.value(),
            # Main Window
            "auto_capture_interval": self.adv_auto_capture_interval.value(),
            "flash_on_duration_ms": self.adv_flash_on_duration_ms.value(),
            "flash_off_duration_ms": self.adv_flash_off_duration_ms.value(),
            "loading_timeout": self.adv_loading_timeout.value(),
            # File Manager
            "image_interpolation": self.adv_image_interpolation.currentText(),
            "video_interpolation": self.adv_video_interpolation.currentText(),
            # Splash
            "loading_dots_interval": self.adv_loading_dots_interval.value(),
            "loading_spinner_interval": self.adv_loading_spinner_interval.value(),
            "loading_fade_duration": self.adv_loading_fade_duration.value(),
            "splash_fade_in_duration": self.adv_splash_fade_in_duration.value(),
            "splash_fade_out_duration": self.adv_splash_fade_out_duration.value(),
            # Hardware / Inicio / Debug
            "gpu_acceleration": self.adv_gpu.isChecked(),
            "auto_start": self.adv_auto_start.isChecked(),
            "remember_last_state": self.adv_remember_state.isChecked(),
            "debug_mode": self.adv_debug.isChecked(),
            "save_logs": self.adv_save_logs.isChecked(),
            "log_level": self.adv_log_level.currentText(),
        })
        settings_manager.save_advanced_settings(new_advanced)

        # === APLICAR PLUGINS (apply_changes de cada ConfigTab) ===
        plugin_reports = []
        staged_advanced_all: Dict[str, Any] = {}
        staged_detection_all: Dict[str, Any] = {}
        staged_plugin_configs: Dict[str, Dict[str, Any]] = {}
        legacy_writes_done = False

        try:
            from core.extension_registry import get_extension_registry
            from core.extensions.interfaces import ConfigTab

            registry = get_extension_registry()
            tabs = registry.get(ConfigTab)
            logger.debug(f"🔧 [save] Procesando {len(tabs)} ConfigTab(s)")

            for tab in tabs:
                tab_id = "unknown"
                try:
                    tab_id = tab.get_id() if hasattr(tab, "get_id") else str(tab)

                    # 1. Llamar a apply_changes (o on_save legacy)
                    method = None
                    if hasattr(tab, "apply_changes"):
                        method = tab.apply_changes
                    elif hasattr(tab, "on_save"):
                        method = tab.on_save

                    success = True
                    if method is not None:
                        try:
                            result = method()
                            success = bool(result) if result is not None else True
                        except Exception as e:
                            logger.error(
                                f"❌ Error en apply_changes de '{tab_id}': {e}",
                                exc_info=True,
                            )
                            success = False

                    plugin_reports.append((tab_id, success))

                    # 2. Recolectar cambios staged SI el tab usa el nuevo patrón
                    if hasattr(tab, "get_staged_changes"):
                        staged = tab.get_staged_changes()
                        adv = staged.get("advanced", {})
                        det = staged.get("detection", {})
                        pc = staged.get("plugin_config", {})

                        if adv:
                            staged_advanced_all.update(adv)
                        if det:
                            staged_detection_all.update(det)
                        if pc:
                            staged_plugin_configs[tab_id] = pc

                        # Si el tab tiene cambios staged → es nuevo patrón
                        if adv or det or pc:
                            logger.debug(
                                f"🔧 [save] '{tab_id}' usa staging "
                                f"(adv={len(adv)}, det={len(det)}, pc={len(pc)})"
                            )
                        else:
                            # NO usó staging → probablemente escribió directo
                            logger.debug(
                                f"🔧 [save] '{tab_id}' sin cambios staged "
                                f"(probablemente legacy directo)"
                            )

                except Exception as e:
                    logger.error(
                        f"❌ Error procesando ConfigTab '{tab_id}': {e}",
                        exc_info=True,
                    )
                    plugin_reports.append((tab_id, False))

            # ✅ 3. Aplicar staged en batch (UNA sola escritura)
            if staged_advanced_all:
                try:
                    from core.settings_manager import settings_manager
                    current = settings_manager.get_advanced_settings()
                    current.update(staged_advanced_all)
                    settings_manager.save_advanced_settings(current)
                    legacy_writes_done = True
                    logger.debug(
                        f"✅ [save] staged_advanced aplicado: "
                        f"{list(staged_advanced_all.keys())[:10]}"
                    )
                except Exception as e:
                    logger.error(f"❌ Error aplicando staged_advanced: {e}", exc_info=True)

            if staged_detection_all:
                try:
                    from core.settings_manager import settings_manager
                    current = settings_manager.get_detection_settings()
                    current.update(staged_detection_all)
                    settings_manager.save_detection_settings(current)
                    logger.debug(
                        f"✅ [save] staged_detection aplicado: "
                        f"{list(staged_detection_all.keys())}"
                    )
                except Exception as e:
                    logger.error(f"❌ Error aplicando staged_detection: {e}", exc_info=True)

            for tab_id, cfg in staged_plugin_configs.items():
                try:
                    from core.settings_manager import settings_manager
                    settings_manager.set_plugin_config(tab_id, cfg)
                except Exception as e:
                    logger.error(f"❌ Error guardando plugin_config de {tab_id}: {e}")

            # ✅ 4. Recargar advanced_config tras todos los cambios
            try:
                from utils.config_loader import advanced_config
                advanced_config.reload()
            except Exception as e:
                logger.debug(f"Error recargando advanced_config: {e}")

        except Exception as e:
            logger.error(f"❌ Error aplicando plugins: {e}", exc_info=True)

        # === ChangeDetector ===
        new_advanced_full = settings_manager.get_advanced_settings()
        new_capture = settings_manager.get_capture_settings()

        def is_camera_count_changed():
            counter_camera = int(settings_manager._settings.value("cameras/count", 0))
            if self.change_counter_camera is None:
                self.change_counter_camera = 0
            else:
                try:
                    self.change_counter_camera = int(self.change_counter_camera)
                except (ValueError, TypeError):
                    self.change_counter_camera = 0

            if counter_camera != self.change_counter_camera:
                self.change_counter_camera = counter_camera
                return True
            return False

        camera_count_changed = is_camera_count_changed()

        report, modules = ChangeDetector.analyze_detailed(
            old_advanced, new_advanced_full,
            None, None,  # detection ahora es plugin
            old_capture, new_capture,
            None, None,  # scan ahora es plugin
            camera_count_changed=camera_count_changed,
        )

        logger.info(f"✅ Configuración guardada. {report}")

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(f"✅ [save] Guardado en {elapsed_ms:.0f}ms")

        self.settings_changed.emit(report, modules)
        self.accept()

    def _apply_staged_advanced(self, changes: dict):
        """Aplica cambios en advanced_settings en batch (UNA escritura)."""
        try:
            from core.settings_manager import settings_manager

            # ✅ Leer el estado actual UNA vez
            current = settings_manager.get_advanced_settings()

            # ✅ Aplicar cambios acumulados de TODOS los tabs
            current.update(changes)

            # ✅ Guardar UNA vez
            settings_manager.save_advanced_settings(current)

            logger.debug(
                f"✅ [staged_advanced] {len(changes)} cambios aplicados: "
                f"{list(changes.keys())[:10]}"
            )
        except Exception as e:
            logger.error(f"❌ Error aplicando staged_advanced: {e}", exc_info=True)

    def _apply_staged_detection(self, changes: dict):
        """Aplica cambios en detection_settings en batch."""
        try:
            from core.settings_manager import settings_manager

            current = settings_manager.get_detection_settings()
            current.update(changes)
            settings_manager.save_detection_settings(current)

            logger.debug(
                f"✅ [staged_detection] {len(changes)} cambios aplicados: "
                f"{list(changes.keys())[:10]}"
            )
        except Exception as e:
            logger.error(f"❌ Error aplicando staged_detection: {e}", exc_info=True)