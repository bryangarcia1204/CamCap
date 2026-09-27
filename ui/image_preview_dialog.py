"""
Diálogo de vista previa de imagen antes de guardar
CON SOPORTE DE MEJORA INTERACTIVA
"""
import cv2
import numpy as np
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, 
                               QLabel, QPushButton, QLineEdit, QFileDialog,
                               QCheckBox, QFrame, QSizePolicy, QMessageBox)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QImage, QResizeEvent, QKeyEvent

from datetime import datetime
import os
from utils.logger import get_logger

logger = get_logger("ImagePreviewDialog")


class ImagePreviewDialog(QDialog):
    """Diálogo para previsualizar y guardar imagen"""
    
    def __init__(self, image: np.ndarray, camera_name: str, parent=None):
        super().__init__(parent)
        self.image = image
        self.original_image = image.copy()
        self.camera_name = camera_name
        self._use_default = False
        self._enhanced = False
        
        self.setWindowTitle("📸 Vista Previa - ProCamera")
        self.setMinimumSize(750, 650)
        self.setModal(True)
        
        self._setup_ui()
        self._display_image()
        logger.debug(f"Preview abierto: {camera_name}")
        
    def _setup_ui(self):
        """Configura la interfaz"""
        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0d1445, stop:1 #2a0a4a);
            }
            QLabel { color: #ffffff; }
            QLineEdit {
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 10px;
                padding: 8px 14px;
                color: #ffffff;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #6a1b9a;
                background: rgba(255,255,255,0.12);
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
            QPushButton[type="secondary"] {
                background: rgba(255,255,255,0.08);
            }
            QPushButton[type="secondary"]:hover {
                background: rgba(255,255,255,0.15);
            }
            QPushButton[type="success"] {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2e7d32, stop:1 #43a047);
            }
            QPushButton[type="success"]:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #388e3c, stop:1 #4caf50);
            }
            QPushButton[type="warning"] {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #ef6c00, stop:1 #f57c00);
            }
            QPushButton[type="warning"]:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #f57c00, stop:1 #fb8c00);
            }
            QCheckBox {
                color: rgba(255,255,255,0.7);
                font-size: 13px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                background: rgba(255,255,255,0.08);
                border: 2px solid rgba(255,255,255,0.15);
            }
            QCheckBox::indicator:checked {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1a237e, stop:1 #4a148c);
                border-color: #6a1b9a;
            }
            QFrame#preview_frame {
                background-color: rgba(0,0,0,0.3);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 12px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 24, 24, 24)
        
        # Header
        header = QHBoxLayout()
        title = QLabel("📸 Vista Previa de la Foto")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffffff;")
        header.addWidget(title)
        header.addStretch()
        
        camera_info = QLabel(f"📷 {self.camera_name}")
        camera_info.setStyleSheet("color: rgba(255,255,255,0.6); font-size: 13px;")
        header.addWidget(camera_info)
        layout.addLayout(header)
        
        # Área de preview
        preview_frame = QFrame()
        preview_frame.setObjectName("preview_frame")
        preview_frame.setMinimumHeight(320)
        preview_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        pv_layout = QVBoxLayout(preview_frame)
        pv_layout.setContentsMargins(8, 8, 8, 8)
        
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumHeight(300)
        self.preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview_label.setStyleSheet("""
            QLabel {
                background-color: rgba(0,0,0,0.2);
                border-radius: 8px;
                color: rgba(255,255,255,0.4);
                font-size: 14px;
            }
        """)
        self.preview_label.setText("Cargando vista previa...")
        pv_layout.addWidget(self.preview_label)
        layout.addWidget(preview_frame)
        
        # Info imagen
        info = QHBoxLayout()
        h, w = self.image.shape[:2]
        size_mb = self.image.nbytes / (1024 * 1024)
        self.info_label = QLabel(f"📐 {w}x{h} px  |  💾 {size_mb:.1f} MB")
        self.info_label.setStyleSheet("color: rgba(255,255,255,0.5); font-size: 12px;")
        info.addWidget(self.info_label)
        info.addStretch()

        # ✅ NUEVO: Extensiones de plugins (botón "✨ Mejorar" etc.)
        self._apply_dialog_extensions(info)

        layout.addLayout(info)
        
        # Formulario
        form_layout = QVBoxLayout()
        form_layout.setSpacing(10)
        
        # Nombre
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Nombre:"))
        
        from core.settings_manager import settings_manager
        settings = settings_manager.get_capture_settings()
        extension = settings.image_format.value
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"{settings.default_name.replace('{timestamp}', timestamp)}_{self.camera_name}"
        
        self.name_edit = QLineEdit()
        self.name_edit.setText(default_name)
        self.name_edit.selectAll()
        self.name_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        name_layout.addWidget(self.name_edit)
        form_layout.addLayout(name_layout)
        
        # Directorio
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel("Directorio:"))
        
        self.dir_edit = QLineEdit()
        self.dir_edit.setText(os.path.expanduser(settings.default_directory))
        self.dir_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        dir_layout.addWidget(self.dir_edit)
        
        self.browse_btn = QPushButton("📁")
        self.browse_btn.setFixedWidth(40)
        self.browse_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 50px;
                color: white;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.15);
            }
        """)
        self.browse_btn.clicked.connect(self._browse_directory)
        dir_layout.addWidget(self.browse_btn)
        form_layout.addLayout(dir_layout)
        
        # Checkbox
        self.default_check = QCheckBox("Usar este directorio como predeterminado")
        form_layout.addWidget(self.default_check)
        
        layout.addLayout(form_layout)
        
        # Botones
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("❌ Cancelar")
        cancel_btn.setProperty("type", "secondary")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        save_btn = QPushButton("💾 Guardar Foto")
        save_btn.setProperty("type", "success")
        save_btn.setMinimumWidth(150)
        save_btn.clicked.connect(self.accept)
        btn_layout.addWidget(save_btn)
        
        layout.addLayout(btn_layout)
    
    def _apply_dialog_extensions(self, info_layout):
        """
        Añade widgets de plugins al diálogo.

        Los plugins registrados como DialogExtension con
        target_dialog="image_preview" pueden añadir botones aquí.
        """
        try:
            from core.extension_registry import get_extension_registry
            from core.extensions.interfaces import DialogExtension

            registry = get_extension_registry()
            if registry is None:
                return

            extensions = [
                ext for ext in registry.get(DialogExtension)
                if ext.get_target_dialog() == "image_preview"
            ]

            extensions = sorted(
                extensions,
                key=lambda e: e.get_priority() if hasattr(e, 'get_priority') else 50,
            )

            for ext in extensions:
                try:
                    widgets = ext.get_widgets(
                        self,
                        image=self.image,
                        camera_name=self.camera_name,
                    )
                    if not widgets:
                        continue
                    for w in widgets:
                        if w is not None:
                            info_layout.addWidget(w)
                except Exception as e:
                    logger.error(
                        f"❌ DialogExtension falló: {e}", exc_info=True
                    )
        except Exception as e:
            logger.debug(f"⚠️ Error aplicando extensiones: {e}")
    
    def _display_image(self):
        """Muestra la imagen"""
        try:
            rgb_image = cv2.cvtColor(self.image, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_image.shape
            bytes_per_line = ch * w
            
            qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
            
            label_width = self.preview_label.width() - 10
            label_height = self.preview_label.height() - 10
            
            if label_width < 10 or label_height < 10:
                label_width = 600
                label_height = 400
            
            pixmap = QPixmap.fromImage(qt_image)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    label_width, label_height,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self.preview_label.setPixmap(scaled)
                self.preview_label.setStyleSheet(
                    "background-color: rgba(0,0,0,0.2); border-radius: 8px;"
                )
        except Exception as e:
            logger.error(f"Error mostrando imagen: {e}")
            self.preview_label.setText(f"❌ Error: {e}")
    
    def _browse_directory(self):
        current = self.dir_edit.text().strip()
        if not os.path.exists(current):
            current = os.path.expanduser("~/Pictures")
        
        dir_path = QFileDialog.getExistingDirectory(
            self, "Seleccionar Directorio", current
        )
        if dir_path:
            self.dir_edit.setText(dir_path)
    
    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self._display_image()
    
    def keyPressEvent(self, event: QKeyEvent):
        """Atajos de teclado"""
        if event.key() == Qt.Key_S and event.modifiers() == Qt.ControlModifier:
            self.accept()
            return
        if event.key() == Qt.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)
    
    def get_save_data(self):
        """Retorna datos para guardar"""
        filename = self.name_edit.text().strip()
        directory = self.dir_edit.text().strip()
        use_default = self.default_check.isChecked()
        
        if not filename:
            return None, None, False
        
        from core.settings_manager import settings_manager
        settings = settings_manager.get_capture_settings()
        extension = settings.image_format.value
        
        if not filename.endswith(f".{extension}"):
            filename = f"{filename}.{extension}"

        frame = self.get_image()
        
        return filename, directory, use_default, frame
    
    def get_image(self) -> np.ndarray:
        """Retorna la imagen (posiblemente mejorada)"""
        return self.image