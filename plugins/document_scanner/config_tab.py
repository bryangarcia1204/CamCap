"""
Tab de configuración del plugin document_scanner.
"""
from PySide6.QtWidgets import (
    QVBoxLayout, QGridLayout, QGroupBox, QLabel,
    QComboBox, QCheckBox, QLineEdit, QPushButton,
    QScrollArea, QWidget, QFileDialog, QHBoxLayout
)
from PySide6.QtCore import Qt

from ui.settings_dialog_base import PluginConfigTab


class DocumentScannerConfigTab(PluginConfigTab):
    """Configuración del escáner de documentos."""

    def build_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)

        # ============ Grupo 1: Escaneo ============
        scan_group = QGroupBox("📄 Escaneo de Documentos (OCR)")
        scan_layout = QGridLayout(scan_group)
        scan_layout.setVerticalSpacing(10)
        scan_layout.setHorizontalSpacing(20)

        self.enabled_cb = QCheckBox("Activar escaneo de documentos")
        scan_layout.addWidget(self.enabled_cb, 0, 0, 1, 2)

        self.auto_correct_cb = QCheckBox("Corregir perspectiva automáticamente")
        scan_layout.addWidget(self.auto_correct_cb, 1, 0, 1, 2)

        scan_layout.addWidget(QLabel("Mejora de imagen:"), 2, 0)
        self.enhance_combo = QComboBox()
        self.enhance_combo.addItems([
            "Automático", "Contraste (CLAHE)",
            "Binarización", "Escala de grises"
        ])
        scan_layout.addWidget(self.enhance_combo, 2, 1)

        scan_layout.addWidget(QLabel("Idioma OCR:"), 3, 0)
        self.lang_combo = QComboBox()
        self.lang_combo.setEditable(True)
        self.lang_combo.addItems([
            "spa+eng", "spa", "eng", "fra", "deu", "por", "ita"
        ])
        scan_layout.addWidget(self.lang_combo, 3, 1)

        scan_layout.addWidget(QLabel("Tesseract:"), 4, 0)
        tesseract_layout = QHBoxLayout()
        self.tesseract_edit = QLineEdit()
        self.tesseract_edit.setPlaceholderText("Auto-detectado")
        tesseract_layout.addWidget(self.tesseract_edit)
        browse_btn = QPushButton("📁")
        browse_btn.clicked.connect(self._browse_tesseract)
        tesseract_layout.addWidget(browse_btn)
        scan_layout.addLayout(tesseract_layout, 4, 1)

        layout.addWidget(scan_group)

        # ============ Grupo 2: Archivos a guardar ============
        save_group = QGroupBox("💾 Archivos a guardar")
        save_layout = QVBoxLayout(save_group)

        self.save_original_cb = QCheckBox("Guardar imagen original")
        save_layout.addWidget(self.save_original_cb)

        self.save_corrected_cb = QCheckBox("Guardar imagen corregida")
        save_layout.addWidget(self.save_corrected_cb)

        self.save_text_cb = QCheckBox("Guardar texto extraído (.txt)")
        save_layout.addWidget(self.save_text_cb)

        layout.addWidget(save_group)
        layout.addStretch()

        scroll.setWidget(content)
        self.layout.addWidget(scroll)

        self._load_values()

    def _browse_tesseract(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar tesseract.exe",
            "C:\\Program Files\\Tesseract-OCR", "Ejecutables (*.exe)"
        )
        if path:
            self.tesseract_edit.setText(path)

    def _load_values(self):
        try:
            from core.settings_manager import settings_manager
            scan = settings_manager.get_scan_settings()

            self.enabled_cb.setChecked(scan.get("enabled", False))
            self.auto_correct_cb.setChecked(scan.get("auto_correct", True))
            self.lang_combo.setCurrentText(scan.get("language", "spa+eng"))
            self.tesseract_edit.setText(scan.get("tesseract_path", ""))
            self.save_original_cb.setChecked(scan.get("save_original", False))
            self.save_corrected_cb.setChecked(scan.get("save_corrected", True))
            self.save_text_cb.setChecked(scan.get("save_text", False))
        except Exception as e:
            print(f"Error cargando valores: {e}")

    def get_config(self):
        return {
            "enabled": self.enabled_cb.isChecked(),
            "auto_correct": self.auto_correct_cb.isChecked(),
            "enhance_mode": "auto",
            "language": self.lang_combo.currentText(),
            "tesseract_path": self.tesseract_edit.text(),
            "save_original": self.save_original_cb.isChecked(),
            "save_corrected": self.save_corrected_cb.isChecked(),
            "save_text": self.save_text_cb.isChecked(),
        }

    def apply_changes(self) -> bool:
        try:
            from core.settings_manager import settings_manager
            return settings_manager.save_scan_settings(self.get_config())
        except Exception as e:
            print(f"Error aplicando config: {e}")
            return False