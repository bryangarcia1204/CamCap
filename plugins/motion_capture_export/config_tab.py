"""
ConfigTab del plugin motion_capture_export.

Muestra:
  - Estado del plugin (tracker cargado o no)
  - Botón para abrir el Motion Capture Studio (diálogo completo)
  - Info sobre dependencias
"""
from PySide6.QtWidgets import (
    QVBoxLayout, QLabel, QPushButton, QGroupBox,
    QHBoxLayout,
)
from PySide6.QtCore import Qt

from ui.settings.settings_dialog_base import PluginConfigTab
from utils.logger import get_logger

logger = get_logger("Plugin.MotionCaptureExport.ConfigTab")


class MotionCaptureExportConfigTab(PluginConfigTab):
    """ConfigTab simplificado: solo un botón que abre el Studio."""

    def build_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(16)

        # === Estado ===
        status_group = QGroupBox("📊 Estado del Plugin")
        status_layout = QVBoxLayout(status_group)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self._update_status()
        status_layout.addWidget(self.status_label)

        layout.addWidget(status_group)

        # === Botón principal ===
        open_group = QGroupBox("🎬 Motion Capture Studio")
        open_layout = QVBoxLayout(open_group)

        desc = QLabel(
            "El Studio te permite cargar un fragmento de video, "
            "configurar el tracker híbrido (YOLO + MediaPipe) y "
            "exportar los landmarks a JSON o CSV para usar en Blender "
            "u otras herramientas de animación."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 12px;")
        open_layout.addWidget(desc)

        open_btn = QPushButton("🎬 Abrir Motion Capture Studio")
        open_btn.setMinimumHeight(50)
        open_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1a237e, stop:1 #4a148c);
                color: white;
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 50px;
                padding: 14px 32px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #283593, stop:1 #6a1b9a);
            }
        """)
        open_btn.clicked.connect(self._open_studio)
        open_layout.addWidget(open_btn)

        layout.addWidget(open_group)

        # === Dependencias ===
        deps_group = QGroupBox("📦 Dependencias")
        deps_layout = QVBoxLayout(deps_group)

        deps_text = QLabel(
            "El plugin requiere:\n"
            "  • ultralytics (YOLOv8-Pose)\n"
            "  • mediapipe (MediaPipe Pose)\n"
            "  • opencv-python\n\n"
            "Instalar:\n"
            "  pip install ultralytics mediapipe opencv-python"
        )
        deps_text.setWordWrap(True)
        deps_text.setStyleSheet(
            "color: rgba(255,255,255,0.6); "
            "font-family: Consolas, monospace; font-size: 11px;"
        )
        deps_layout.addWidget(deps_text)

        layout.addWidget(deps_group)

        layout.addStretch()
        self.layout.addLayout(layout)

    def _update_status(self):
        """Actualiza el label de estado según el tracker del plugin."""
        try:
            from core.plugin_api import get_plugin_manager
            pm = get_plugin_manager()
            if pm is None:
                self.status_label.setText("⚠️ PluginManager no disponible")
                return

            plugin = pm.get("motion_capture_export")
            if plugin is None:
                self.status_label.setText("❌ Plugin no cargado")
                return

            if plugin._tracker is not None:
                self.status_label.setText(
                    "✅ Tracker cargado (YOLO + MediaPipe listos)"
                )
                self.status_label.setStyleSheet(
                    "color: #4CAF50; font-size: 13px; font-weight: bold;"
                )
            else:
                self.status_label.setText(
                    "⚠️ Tracker NO cargado.\n"
                    "Instala las dependencias y reinicia la app."
                )
                self.status_label.setStyleSheet(
                    "color: #FF9800; font-size: 13px; font-weight: bold;"
                )
        except Exception as e:
            self.status_label.setText(f"Error: {e}")
            self.status_label.setStyleSheet("color: #f44336;")

    def _open_studio(self):
        """Abre el diálogo Motion Capture Studio."""
        try:
            from core.plugin_api import get_plugin_manager
            from plugins.motion_capture_export.motion_capture_dialog import (
                MotionCaptureDialog,
            )

            pm = get_plugin_manager()
            if pm is None:
                logger.error("PluginManager no disponible")
                return

            plugin = pm.get("motion_capture_export")
            if plugin is None:
                logger.error("Plugin no cargado")
                return

            # Abrir como diálogo no modal para que el usuario pueda
            # seguir usando el resto de la app mientras procesa
            dialog = MotionCaptureDialog(plugin, parent=self.window())
            dialog.setAttribute(Qt.WA_DeleteOnClose)
            dialog.show()
        except Exception as e:
            logger.error(f"Error abriendo Studio: {e}", exc_info=True)

    def apply_changes(self) -> bool:
        """No hay nada que guardar aquí (el diálogo guarda su propia config)."""
        return True