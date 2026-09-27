"""
Diálogo para instalar un plugin desde ZIP.
"""
import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QFileDialog, QMessageBox,
    QProgressBar, QTextEdit
)
from PySide6.QtCore import Qt

from utils.logger import get_logger

logger = get_logger("PluginInstallDialog")


class PluginInstallDialog(QDialog):
    """Diálogo para instalar un plugin desde un ZIP."""

    def __init__(self, plugin_manager, parent=None):
        super().__init__(parent)
        self.plugin_manager = plugin_manager
        self.selected_zip = ""
        self.installed_plugin_name = None

        self.setWindowTitle("📦 Instalar Plugin desde ZIP")
        self.setMinimumSize(600, 400)
        self.setModal(True)
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0d1445, stop:1 #2a0a4a);
            }
            QLabel { color: white; }
            QLineEdit {
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 8px;
                padding: 8px 12px;
                color: white;
                font-size: 12px;
            }
            QTextEdit {
                background: rgba(0, 0, 0, 0.3);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 8px;
                padding: 8px;
                color: rgba(255,255,255,0.85);
                font-family: Consolas, monospace;
                font-size: 11px;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1a237e, stop:1 #4a148c);
                color: white;
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 6px;
                padding: 8px 20px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #283593, stop:1 #6a1b9a);
            }
            QPushButton[type="secondary"] {
                background: rgba(255,255,255,0.08);
            }
            QPushButton:disabled {
                background: #333;
                color: #666;
            }
            QProgressBar {
                background: rgba(255,255,255,0.1);
                border: none;
                border-radius: 4px;
                height: 8px;
                text-align: center;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4da0c4, stop:1 #6a1b9a);
                border-radius: 4px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # === Título ===
        title = QLabel("📦 Instalar Plugin")
        title.setStyleSheet(
            "font-size: 20px; font-weight: bold; color: #4da0c4;"
        )
        layout.addWidget(title)

        desc = QLabel(
            "Selecciona un archivo .zip que contenga un plugin de ProCamera.\n"
            "El plugin será validado antes de instalarse."
        )
        desc.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 12px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # === Selector de archivo ===
        file_row = QHBoxLayout()
        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText("Selecciona un archivo .zip...")
        self.file_edit.setReadOnly(True)
        file_row.addWidget(self.file_edit, 1)

        browse_btn = QPushButton("📁 Buscar...")
        browse_btn.clicked.connect(self._browse_zip)
        file_row.addWidget(browse_btn)

        layout.addLayout(file_row)

        # === Log ===
        log_label = QLabel("📋 Log de instalación:")
        log_label.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 12px;")
        layout.addWidget(log_label)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setPlaceholderText("Esperando archivo...")
        layout.addWidget(self.log_text, 1)

        # === Progress ===
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # === Botones ===
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.install_btn = QPushButton("📦 Instalar")
        self.install_btn.setEnabled(False)
        self.install_btn.clicked.connect(self._install)
        btn_row.addWidget(self.install_btn)

        cancel_btn = QPushButton("Cancelar")
        cancel_btn.setProperty("type", "secondary")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        layout.addLayout(btn_row)

    def _browse_zip(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar plugin .zip",
            "",
            "Plugin files (*.zip)",
        )
        if path:
            self.selected_zip = path
            self.file_edit.setText(path)
            self.install_btn.setEnabled(True)
            self._log(f"📦 ZIP seleccionado: {path}")

    def _install(self):
        if not self.selected_zip:
            return

        self.install_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(20)
        self._log("🔍 Validando ZIP...")

        try:
            ok, msg, plugin_name = self.plugin_manager.install_from_zip(
                self.selected_zip
            )
            self.progress.setValue(80)

            if not ok:
                self._log(f"❌ {msg}")
                self.progress.setValue(0)
                self.progress.setVisible(False)
                self.install_btn.setEnabled(True)
                QMessageBox.critical(self, "Error", msg)
                return

            self._log(f"✅ {msg}")
            self.progress.setValue(100)
            self.installed_plugin_name = plugin_name

            QMessageBox.information(
                self,
                "Instalado",
                f"Plugin '{plugin_name}' instalado correctamente.\n\n"
                f"El plugin aparecerá en la lista después de refrescar.",
            )
            self.accept()

        except Exception as e:
            logger.error(f"Error instalando: {e}", exc_info=True)
            self._log(f"❌ Error: {e}")
            self.progress.setValue(0)
            self.progress.setVisible(False)
            self.install_btn.setEnabled(True)
            QMessageBox.critical(self, "Error", str(e))

    def _log(self, text: str):
        self.log_text.append(text)