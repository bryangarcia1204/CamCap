"""
Diálogo con información detallada de un plugin.
"""
import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFormLayout, QGroupBox, QScrollArea,
    QWidget, QTextEdit, QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

from utils.logger import get_logger

logger = get_logger("PluginInfoDialog")


class PluginInfoDialog(QDialog):
    """Diálogo con info completa de un plugin."""

    def __init__(self, info: dict, parent=None):
        super().__init__(parent)
        self.info = info
        self.setWindowTitle(f"🔌 {info.get('name', 'Plugin')}")
        self.setMinimumSize(700, 600)
        self.setModal(True)
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0d1445, stop:1 #2a0a4a);
            }
            QLabel { color: white; }
            QGroupBox {
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 10px;
                margin-top: 10px;
                padding-top: 14px;
                font-weight: bold;
                color: #4da0c4;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 8px;
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
            QPushButton[type="secondary"]:hover {
                background: rgba(255,255,255,0.15);
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # === Título ===
        title = QLabel(f"{self.info.get('name', 'Plugin')}")
        title.setStyleSheet(
            "font-size: 22px; font-weight: bold; color: #4da0c4;"
        )
        layout.addWidget(title)

        # === Scroll area ===
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        c_layout = QVBoxLayout(content)
        c_layout.setSpacing(16)
        c_layout.setContentsMargins(0, 0, 0, 0)

        # === Info general ===
        general_group = QGroupBox("📋 Información General")
        general_layout = QFormLayout(general_group)
        general_layout.setSpacing(8)

        general_layout.addRow(
            "Nombre:",
            QLabel(self.info.get("name", "—"))
        )
        general_layout.addRow(
            "Versión:",
            QLabel(self.info.get("version", "—"))
        )
        general_layout.addRow(
            "Autor:",
            QLabel(self.info.get("author", "—") or "—")
        )
        general_layout.addRow(
            "Descripción:",
            self._wrap_label(self.info.get("description", "—") or "—")
        )

        # Estado
        status_text = "❌ FALLIDO" if self.info.get("is_failed") else \
                      "✅ ACTIVO" if self.info.get("is_enabled") else \
                      "⏸️ INACTIVO" if self.info.get("is_loaded") else \
                      "⏹️ DESCARGADO"
        status_color = "#f44336" if self.info.get("is_failed") else \
                       "#4CAF50" if self.info.get("is_enabled") else \
                       "#FF9800" if self.info.get("is_loaded") else "#888"

        status_lbl = QLabel(status_text)
        status_lbl.setStyleSheet(
            f"color: {status_color}; font-weight: bold;"
        )
        general_layout.addRow("Estado:", status_lbl)

        # Origen
        origin_text = "📦 ZIP" if self.info.get("origin") == "zip" else "📁 Directorio"
        general_layout.addRow("Origen:", QLabel(origin_text))

        c_layout.addWidget(general_group)

        # === Path ===
        path_group = QGroupBox("📁 Ubicación")
        path_layout = QVBoxLayout(path_group)

        path_lbl = QLabel(self.info.get("path", "—"))
        path_lbl.setStyleSheet(
            "color: rgba(255,255,255,0.7); "
            "font-family: Consolas, monospace; font-size: 11px;"
        )
        path_lbl.setWordWrap(True)
        path_layout.addWidget(path_lbl)

        if self.info.get("zip_path"):
            zip_lbl = QLabel(f"ZIP original: {self.info['zip_path']}")
            zip_lbl.setStyleSheet(
                "color: rgba(255,255,255,0.5); "
                "font-family: Consolas, monospace; font-size: 11px;"
            )
            zip_lbl.setWordWrap(True)
            path_layout.addWidget(zip_lbl)

        c_layout.addWidget(path_group)

        # === Dependencias ===
        deps = self.info.get("dependencies", [])
        if deps:
            deps_group = QGroupBox("📦 Dependencias")
            deps_layout = QVBoxLayout(deps_group)
            for dep in deps:
                dep_lbl = QLabel(f"• {dep}")
                dep_lbl.setStyleSheet("color: rgba(255,255,255,0.8);")
                deps_layout.addWidget(dep_lbl)
            c_layout.addWidget(deps_group)

        # === Capabilities ===
        caps = self.info.get("capabilities", [])
        caps_group = QGroupBox("🔒 Capabilities")
        caps_layout = QVBoxLayout(caps_group)

        if not caps:
            no_caps = QLabel("Sin capabilities declaradas")
            no_caps.setStyleSheet(
                "color: rgba(255,255,255,0.5); font-style: italic;"
            )
            caps_layout.addWidget(no_caps)
        else:
            for cap in caps:
                cap_lbl = QLabel(f"✅ {cap}")
                cap_lbl.setStyleSheet(
                    "color: rgba(76, 175, 80, 0.9); "
                    "font-family: Consolas, monospace; font-size: 12px;"
                )
                caps_layout.addWidget(cap_lbl)

        c_layout.addWidget(caps_group)

        # === Extensiones registradas ===
        extensions = self.info.get("extensions", [])
        ext_group = QGroupBox("🧩 Extensiones Registradas")
        ext_layout = QVBoxLayout(ext_group)

        if not extensions:
            no_ext = QLabel("Sin extensiones registradas")
            no_ext.setStyleSheet(
                "color: rgba(255,255,255,0.5); font-style: italic;"
            )
            ext_layout.addWidget(no_ext)
        else:
            for ext in extensions:
                ext_lbl = QLabel(
                    f"• {ext['interface']} (prio {ext['priority']})"
                )
                ext_lbl.setStyleSheet(
                    "color: rgba(77, 160, 196, 0.9); "
                    "font-family: Consolas, monospace; font-size: 12px;"
                )
                ext_layout.addWidget(ext_lbl)

        c_layout.addWidget(ext_group)
        c_layout.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll)

        # === Botones ===
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        if self.info.get("path") and os.path.isdir(self.info["path"]):
            open_btn = QPushButton("📂 Abrir carpeta")
            open_btn.setProperty("type", "secondary")
            open_btn.clicked.connect(self._open_folder)
            btn_row.addWidget(open_btn)

        copy_btn = QPushButton("📋 Copiar info")
        copy_btn.setProperty("type", "secondary")
        copy_btn.clicked.connect(self._copy_info)
        btn_row.addWidget(copy_btn)

        close_btn = QPushButton("Cerrar")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)

    def _wrap_label(self, text: str, max_width: int = 500) -> QLabel:
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setMaximumWidth(max_width)
        return lbl

    def _open_folder(self):
        path = self.info.get("path")
        if not path or not os.path.isdir(path):
            return
        try:
            import subprocess
            import platform
            system = platform.system()
            if system == "Windows":
                os.startfile(path)
            elif system == "Darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            QMessageBox.warning(self, "Error", f"No se pudo abrir: {e}")

    def _copy_info(self):
        lines = [
            f"Plugin: {self.info.get('name')}",
            f"Versión: {self.info.get('version')}",
            f"Autor: {self.info.get('author') or '—'}",
            f"Descripción: {self.info.get('description') or '—'}",
            f"Estado: {self.info.get('is_enabled') and 'Activo' or 'Inactivo'}",
            f"Path: {self.info.get('path')}",
            "",
            "Dependencias:",
            *[f"  - {d}" for d in self.info.get("dependencies", [])],
            "",
            "Capabilities:",
            *[f"  - {c}" for c in self.info.get("capabilities", [])],
            "",
            "Extensiones:",
            *[f"  - {e['interface']} (prio {e['priority']})"
              for e in self.info.get("extensions", [])],
        ]
        text = "\n".join(lines)
        QGuiApplication.clipboard().setText(text)
        QMessageBox.information(self, "Copiado", "Info copiada al portapapeles")