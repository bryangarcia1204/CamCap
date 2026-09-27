"""
Visor de imágenes con zoom
"""
import os
import cv2
import numpy as np
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, 
                               QLabel, QPushButton, QSlider, QScrollArea)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QImage
from utils.logger import get_logger

logger = get_logger("ImagePreview")


class ImagePreview(QWidget):
    """Visor de imágenes con zoom"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_image = None
        self.zoom_level = 1.0
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)
        
        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #666;
                font-size: 16px;
            }
            QPushButton:hover { color: #f44336; }
        """)
        toolbar.addWidget(self.close_btn)
        
        self.file_label = QLabel("Sin archivo")
        self.file_label.setStyleSheet("color: #888;")
        toolbar.addWidget(self.file_label)
        
        toolbar.addStretch()
        
        zoom_in = QPushButton("🔍+")
        zoom_in.clicked.connect(self._zoom_in)
        toolbar.addWidget(zoom_in)
        
        zoom_out = QPushButton("🔍-")
        zoom_out.clicked.connect(self._zoom_out)
        toolbar.addWidget(zoom_out)
        
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(10, 200)
        self.zoom_slider.setValue(100)
        self.zoom_slider.valueChanged.connect(self._on_zoom_slider)
        self.zoom_slider.setMaximumWidth(100)
        toolbar.addWidget(self.zoom_slider)
        
        layout.addLayout(toolbar)
        
        # Área de imagen
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                border: 1px solid #404040;
                border-radius: 4px;
                background-color: #1a1a1a;
            }
        """)
        
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("""
            QLabel {
                background-color: #1a1a1a;
                padding: 10px;
            }
        """)
        
        scroll.setWidget(self.image_label)
        layout.addWidget(scroll)
        
        self.hide()
    
    def set_image(self, image_path: str):
        """Carga y muestra imagen"""
        try:
            with open(image_path, 'rb') as f:
                data = f.read()
            
            arr = np.frombuffer(data, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            
            if img is not None:
                rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb.shape
                bytes_per_line = ch * w
                qt_img = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
                
                self.current_image = qt_img
                self.zoom_level = 1.0
                self.zoom_slider.setValue(100)
                
                self.file_label.setText(os.path.basename(image_path))
                self._display_image()
                self.show()
                logger.debug(f"Imagen cargada: {image_path}")
        except Exception as e:
            logger.error(f"Error cargando imagen: {e}")
    
    def _display_image(self):
        if self.current_image is not None:
            width = int(self.current_image.width() * self.zoom_level)
            height = int(self.current_image.height() * self.zoom_level)
            
            pixmap = QPixmap.fromImage(self.current_image)
            scaled = pixmap.scaled(
                width, height,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.image_label.setPixmap(scaled)
    
    def _zoom_in(self):
        self.zoom_level = min(5.0, self.zoom_level * 1.2)
        self.zoom_slider.setValue(int(self.zoom_level * 100))
        self._display_image()
    
    def _zoom_out(self):
        self.zoom_level = max(0.1, self.zoom_level / 1.2)
        self.zoom_slider.setValue(int(self.zoom_level * 100))
        self._display_image()
    
    def _on_zoom_slider(self, value: int):
        self.zoom_level = value / 100.0
        self._display_image()