"""
Diálogo con información detallada de un plugin.

Incluye:
  - Info general (nombre, versión, autor, estado, origen)
  - README.md renderizado (si existe)
  - Dependencias
  - Capabilities
  - Extensiones registradas
"""
import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFormLayout, QGroupBox, QScrollArea,
    QWidget, QTextBrowser, QMessageBox, QTabWidget,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

from ui.markdown_viewer import MarkdownViewer
from utils.logger import get_logger

logger = get_logger("PluginInfoDialog")


class PluginInfoDialog(QDialog):
    """Diálogo con info completa de un plugin."""

    def __init__(self, info: dict, parent=None):
        super().__init__(parent)
        self.info = info
        self.setWindowTitle(f"🔌 {info.get('name', 'Plugin')}")
        self.setMinimumSize(1000, 800)
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
            QTextBrowser {
                background: rgba(0,0,0,0.3);
                color: #e0e0e0;
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 6px;
                padding: 12px;
                font-size: 13px;
            }
            QTabWidget::pane {
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 6px;
                background: rgba(0,0,0,0.15);
            }
            QTabBar::tab {
                background: rgba(255,255,255,0.05);
                color: white;
                padding: 8px 18px;
                border: 1px solid rgba(255,255,255,0.1);
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1a237e, stop:1 #4a148c);
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # === Título ===
        title = QLabel(self.info.get("name", "Plugin"))
        title.setStyleSheet(
            "font-size: 22px; font-weight: bold; color: #4da0c4;"
        )
        layout.addWidget(title)

        # === Tabs: Información / README ===
        tabs = QTabWidget()

        # --- Tab 1: Información ---
        tabs.addTab(self._create_info_tab(), "📋 Información")

        # --- Tab 2: README (si existe) ---
        if self.info.get("has_readme"):
            tabs.addTab(
                self._create_readme_tab(),
                "📖 README",
            )

        layout.addWidget(tabs, 1)

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

    # ==================== TAB INFO ====================

    def _create_info_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        c_layout = QVBoxLayout(content)
        c_layout.setSpacing(16)
        c_layout.setContentsMargins(0, 0, 0, 0)

        # --- Info general ---
        general_group = QGroupBox("📋 Información General")
        general_layout = QFormLayout(general_group)
        general_layout.setSpacing(8)

        general_layout.addRow("Nombre:", QLabel(self.info.get("name", "—")))
        general_layout.addRow("Versión:", QLabel(self.info.get("version", "—")))
        general_layout.addRow("Autor:", QLabel(self.info.get("author", "—") or "—"))

        desc = self.info.get("description", "") or "—"
        desc_label = QLabel(desc)
        desc_label.setWordWrap(True)
        desc_label.setMaximumWidth(500)
        general_layout.addRow("Descripción:", desc_label)

        # Estado
        status_text = "❌ FALLIDO" if self.info.get("is_failed") else \
                      "✅ ACTIVO" if self.info.get("is_enabled") else \
                      "⏸️ INACTIVO" if self.info.get("is_loaded") else \
                      "⏹️ DESCARGADO"
        status_color = "#f44336" if self.info.get("is_failed") else \
                       "#4CAF50" if self.info.get("is_enabled") else \
                       "#FF9800" if self.info.get("is_loaded") else "#888"
        status_lbl = QLabel(status_text)
        status_lbl.setStyleSheet(f"color: {status_color}; font-weight: bold;")
        general_layout.addRow("Estado:", status_lbl)

        # Origen
        origin_text = "📦 ZIP" if self.info.get("origin") == "zip" else "📁 Directorio"
        general_layout.addRow("Origen:", QLabel(origin_text))

        c_layout.addWidget(general_group)

        # --- Ubicación ---
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

        # --- Dependencias ---
        deps = self.info.get("dependencies", [])
        if deps:
            deps_group = QGroupBox("📦 Dependencias")
            deps_layout = QVBoxLayout(deps_group)
            for dep in deps:
                dep_lbl = QLabel(f"• {dep}")
                dep_lbl.setStyleSheet("color: rgba(255,255,255,0.8);")
                deps_layout.addWidget(dep_lbl)
            c_layout.addWidget(deps_group)

        # --- Capabilities ---
        caps = self.info.get("capabilities", [])
        caps_group = QGroupBox("🔒 Capabilities")
        caps_layout = QVBoxLayout(caps_group)
        if not caps:
            no_caps = QLabel("Sin capabilities declaradas")
            no_caps.setStyleSheet("color: rgba(255,255,255,0.5); font-style: italic;")
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

        # --- Extensiones registradas ---
        extensions = self.info.get("extensions", [])
        ext_group = QGroupBox("🧩 Extensiones Registradas")
        ext_layout = QVBoxLayout(ext_group)
        if not extensions:
            no_ext = QLabel("Sin extensiones registradas")
            no_ext.setStyleSheet("color: rgba(255,255,255,0.5); font-style: italic;")
            ext_layout.addWidget(no_ext)
        else:
            for ext in extensions:
                ext_lbl = QLabel(f"• {ext['interface']} (prio {ext['priority']})")
                ext_lbl.setStyleSheet(
                    "color: rgba(77, 160, 196, 0.9); "
                    "font-family: Consolas, monospace; font-size: 12px;"
                )
                ext_layout.addWidget(ext_lbl)
        c_layout.addWidget(ext_group)

        # --- README (si existe, mostrar ruta) ---
        if self.info.get("has_readme"):
            readme_info_group = QGroupBox("📖 README")
            readme_info_layout = QVBoxLayout(readme_info_group)
            rp = self.info.get("readme_path", "")
            rp_lbl = QLabel(rp)
            rp_lbl.setStyleSheet(
                "color: rgba(255,255,255,0.6); "
                "font-family: Consolas, monospace; font-size: 11px;"
            )
            rp_lbl.setWordWrap(True)
            readme_info_layout.addWidget(rp_lbl)
            size_kb = len(self.info.get("readme_content", "")) / 1024
            readme_info_layout.addWidget(
                QLabel(f"Tamaño: {size_kb:.1f} KB")
            )
            c_layout.addWidget(readme_info_group)

        c_layout.addStretch()
        scroll.setWidget(content)
        return scroll

    # ==================== TAB README ====================

    def _create_readme_tab(self) -> QWidget:
        """Crea la pestaña de README usando MarkdownViewer nivel GitHub."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Crear viewer
        self._readme_viewer = MarkdownViewer(theme="dark")

        content = self.info.get("readme_content", "")
        readme_path = self.info.get("readme_path", "")

        # Si tenemos el path del README, lo usamos para resolver
        # imágenes y links relativos correctamente.
        if readme_path and os.path.isfile(readme_path):
            self._readme_viewer.load_file(readme_path)
        elif content.strip():
            self._readme_viewer.load_markdown(content)
        else:
            self._readme_viewer.load_markdown(
                "*Este plugin no tiene README.md*"
            )

        # Conectar clicks de links
        self._readme_viewer.link_clicked.connect(self._on_readme_link)

        layout.addWidget(self._readme_viewer)
        return widget

    def _on_readme_link(self, url_str: str):
        """Maneja clicks en links del README."""
        logger.debug(f"Link clickeado en README: {url_str}")

    # ==================== ACCIONES ====================

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

    def _open_readme_external(self):
        path = self.info.get("readme_path")
        if not path or not os.path.isfile(path):
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
            f"Estado: {'Activo' if self.info.get('is_enabled') else 'Inactivo'}",
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