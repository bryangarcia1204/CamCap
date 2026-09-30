"""
ConfigTab del plugin image_enhancer.

Además de los ajustes por defecto, incluye un botón para abrir
el editor de imágenes directamente desde la configuración,
sin necesidad de ir a la vista previa de captura.
"""
import os
from PySide6.QtWidgets import (
    QVBoxLayout, QGridLayout, QGroupBox, QLabel,
    QComboBox, QCheckBox, QPushButton, QScrollArea,
    QWidget, QHBoxLayout, QFileDialog, QMessageBox,
    QDialog,
)
from PySide6.QtCore import Qt

from ui.settings_dialog_base import PluginConfigTab
from utils.logger import get_logger

logger = get_logger("Plugin.ImageEnhancerConfigTab")


class ImageEnhancerConfigTab(PluginConfigTab):
    """Configuración del plugin image_enhancer."""

    SCHEMA = {
        "image_enhancer_default_preset": {"type": "str", "default": "auto"},
        "image_enhancer_auto_on_capture": {"type": "bool", "default": False},
        "image_enhancer_auto_on_scan": {"type": "bool", "default": True},
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

        # ============ Grupo 1: Editor rápido ============
        editor_group = QGroupBox("🎨 Editor de Imágenes")
        editor_layout = QVBoxLayout(editor_group)

        editor_desc = QLabel(
            "Abre el editor de imágenes para mejorar cualquier foto "
            "de tu disco. Aplica presets, ajusta brillo/contraste, "
            "reduce ruido, etc."
        )
        editor_desc.setStyleSheet(
            "color: rgba(255,255,255,0.6); font-size: 11px;"
        )
        editor_desc.setWordWrap(True)
        editor_layout.addWidget(editor_desc)

        open_editor_btn = QPushButton("🎨 Abrir Editor de Imágenes")
        open_editor_btn.setMinimumHeight(40)
        open_editor_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #ef6c00, stop:1 #f57c00);
                color: white;
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 50px;
                padding: 10px 24px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #f57c00, stop:1 #fb8c00);
            }
        """)
        open_editor_btn.clicked.connect(self._open_editor)
        editor_layout.addWidget(open_editor_btn)

        layout.addWidget(editor_group)

        # ============ Grupo 2: Preset por defecto ============
        preset_group = QGroupBox("🎯 Preset por defecto")
        preset_layout = QGridLayout(preset_group)
        preset_layout.setVerticalSpacing(10)
        preset_layout.setHorizontalSpacing(20)

        preset_layout.addWidget(QLabel("Preset:"), 0, 0)
        self.preset_combo = QComboBox()
        self.preset_combo.addItems([
            "auto", "documento", "foto", "noche",
            "retrato", "paisaje", "ninguno",
        ])
        preset_layout.addWidget(self.preset_combo, 0, 1)

        layout.addWidget(preset_group)

        # ============ Grupo 3: Automatización ============
        auto_group = QGroupBox("🤖 Automatización")
        auto_layout = QVBoxLayout(auto_group)

        self.auto_capture_cb = QCheckBox(
            "Aplicar mejora automática al capturar"
        )
        auto_layout.addWidget(self.auto_capture_cb)

        self.auto_scan_cb = QCheckBox(
            "Aplicar mejora automática al escanear documentos"
        )
        auto_layout.addWidget(self.auto_scan_cb)

        layout.addWidget(auto_group)

        # ============ Info ============
        info_group = QGroupBox("ℹ️ Info")
        info_layout = QVBoxLayout(info_group)

        info_text = QLabel(
            "💡 Los controles finos (brillo, contraste, gamma, etc.) "
            "se ajustan por-imagen desde el diálogo de edición.\n\n"
            "Los presets se aplican con un solo clic desde el editor."
        )
        info_text.setStyleSheet(
            "color: rgba(255,255,255,0.6); font-size: 11px;"
        )
        info_text.setWordWrap(True)
        info_layout.addWidget(info_text)

        layout.addWidget(info_group)
        layout.addStretch()

        scroll.setWidget(content)
        self.layout.addWidget(scroll)

        self._load_values()

    # ==================== ABRIR EDITOR ====================

    def _open_editor(self):
        """Abre un archivo de imagen y lanza el editor."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar imagen para editar",
            os.path.expanduser("~/Pictures"),
            "Imágenes (*.jpg *.jpeg *.png *.bmp *.tiff *.webp);;Todos (*)",
        )
        if not path:
            return

        try:
            import cv2
            import numpy as np

            # Leer la imagen (con soporte de caracteres no-ASCII)
            try:
                with open(path, "rb") as f:
                    data = f.read()
                arr = np.frombuffer(data, dtype=np.uint8)
                image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            except Exception as e:
                QMessageBox.critical(
                    self, "Error", f"No se pudo leer la imagen:\n{e}"
                )
                return

            if image is None:
                QMessageBox.warning(
                    self, "Error", "No se pudo decodificar la imagen."
                )
                return

            logger.debug(f"🎨 Editor abierto: {path} ({image.shape})")

            # Abrir el diálogo de edición
            from .enhance_dialog import ImageEnhanceDialog

            dialog = ImageEnhanceDialog(image, parent=self.window())
            if dialog.exec() != QDialog.Accepted:
                logger.debug("Editor cancelado por el usuario")
                return

            # Obtener la imagen mejorada
            result, was_enhanced = dialog.get_result()
            if result is None:
                return

            if not was_enhanced:
                QMessageBox.information(
                    self, "Sin cambios",
                    "No se aplicó ninguna mejora."
                )
                return

            # Preguntar dónde guardar
            self._save_enhanced_image(result, path)

        except ImportError as e:
            QMessageBox.critical(
                self, "Faltan dependencias",
                f"Falta alguna dependencia:\n{e}\n\n"
                f"Instala con:\n  pip install opencv-python numpy"
            )
        except Exception as e:
            logger.error(f"Error abriendo editor: {e}", exc_info=True)
            QMessageBox.critical(
                self, "Error", f"Error inesperado:\n{e}"
            )

    def _save_enhanced_image(self, image, original_path: str):
        """Pregunta dónde guardar la imagen mejorada y la guarda."""
        # Sugerir un nombre por defecto al lado del original
        base, ext = os.path.splitext(original_path)
        default_name = f"{base}_enhanced{ext}"

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar imagen mejorada",
            default_name,
            "Imágenes (*.jpg *.jpeg *.png *.bmp *.tiff *.webp);;Todos (*)",
        )
        if not save_path:
            return

        try:
            import cv2

            # Codificar según la extensión
            ext = os.path.splitext(save_path)[1].lower()
            params = []
            if ext in (".jpg", ".jpeg"):
                params = [cv2.IMWRITE_JPEG_QUALITY, 95]
            elif ext == ".png":
                params = [cv2.IMWRITE_PNG_COMPRESSION, 3]
            elif ext == ".webp":
                params = [cv2.IMWRITE_WEBP_QUALITY, 95]

            success, buffer = cv2.imencode(ext, image, params)
            if not success:
                raise RuntimeError("cv2.imencode falló")

            with open(save_path, "wb") as f:
                f.write(buffer.tobytes())

            size_kb = os.path.getsize(save_path) / 1024
            logger.info(f"💾 Imagen guardada: {save_path} ({size_kb:.1f} KB)")

            QMessageBox.information(
                self, "Guardado",
                f"Imagen mejorada guardada en:\n{save_path}\n\n"
                f"({size_kb:.1f} KB)"
            )

        except Exception as e:
            logger.error(f"Error guardando imagen: {e}", exc_info=True)
            QMessageBox.critical(
                self, "Error", f"No se pudo guardar:\n{e}"
            )

    # ==================== CARGA / GUARDADO ====================

    def _load_values(self):
        try:
            self.preset_combo.setCurrentText(
                self._config.get("image_enhancer_default_preset", "auto")
            )
            self.auto_capture_cb.setChecked(
                self._config.get("image_enhancer_auto_on_capture", False)
            )
            self.auto_scan_cb.setChecked(
                self._config.get("image_enhancer_auto_on_scan", True)
            )
        except Exception as e:
            logger.error(f"Error cargando valores: {e}")

    def get_config(self):
        return {
            "image_enhancer_default_preset": self.preset_combo.currentText(),
            "image_enhancer_auto_on_capture": self.auto_capture_cb.isChecked(),
            "image_enhancer_auto_on_scan": self.auto_scan_cb.isChecked(),
        }

    def apply_changes(self) -> bool:
        """Guarda la config del tab (staging)."""
        try:
            self.stage_plugin_config(
                "image_enhancer_default_preset",
                self.preset_combo.currentText(),
            )
            self.stage_plugin_config(
                "image_enhancer_auto_on_capture",
                self.auto_capture_cb.isChecked(),
            )
            self.stage_plugin_config(
                "image_enhancer_auto_on_scan",
                self.auto_scan_cb.isChecked(),
            )
            return True
        except Exception as e:
            logger.error(f"Error guardando config: {e}", exc_info=True)
            return False