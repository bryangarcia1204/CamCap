"""
Card widget para mostrar un plugin en el PluginManagerDialog.
"""
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QMenu, QMessageBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QCursor

from utils.logger import get_logger

logger = get_logger("PluginCard")


class PluginCard(QFrame):
    """Card que muestra info de un plugin con acciones."""

    configure_requested = Signal(str)      # plugin_name
    toggle_requested = Signal(str, bool)   # plugin_name, enable
    info_requested = Signal(str)           # plugin_name
    uninstall_requested = Signal(str)      # plugin_name
    reload_requested = Signal(str)         # plugin_name

    def __init__(self, info: dict, parent=None):
        super().__init__(parent)
        self.info = info
        self.plugin_name = info["name"]

        self.setObjectName("PluginCard")
        self.setFrameShape(QFrame.StyledPanel)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._setup_ui()
        self._apply_state_style()

    # ==================== UI ====================

    def _setup_ui(self):
        self.setMinimumHeight(110)
        self.setStyleSheet("""
            QFrame#PluginCard {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
                padding: 12px;
            }
            QFrame#PluginCard:hover {
                background: rgba(255, 255, 255, 0.07);
            }
            QFrame#PluginCard[state="enabled"] {
                border-left: 4px solid #4CAF50;
            }
            QFrame#PluginCard[state="disabled"] {
                border-left: 4px solid #FF9800;
            }
            QFrame#PluginCard[state="failed"] {
                border-left: 4px solid #f44336;
            }
            QFrame#PluginCard[state="unloaded"] {
                border-left: 4px solid #666;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(4, 4, 4, 4)

        # === Header (icono + nombre + versión + estado) ===
        header = QHBoxLayout()
        header.setSpacing(10)

        # Icono
        self.icon_label = QLabel(self._get_icon())
        self.icon_label.setStyleSheet("font-size: 28px;")
        self.icon_label.setFixedWidth(40)
        self.icon_label.setAlignment(Qt.AlignCenter)
        header.addWidget(self.icon_label)

        # Nombre + versión
        name_box = QVBoxLayout()
        name_box.setSpacing(2)

        self.name_label = QLabel(self.info["name"])
        self.name_label.setStyleSheet(
            "font-size: 15px; font-weight: bold; color: #ffffff;"
        )
        name_box.addWidget(self.name_label)

        meta_text = f"v{self.info['version']}"
        if self.info.get("author"):
            meta_text += f" · {self.info['author']}"
        if self.info.get("origin") == "zip":
            meta_text += " · 📦 ZIP"
        else:
            meta_text += " · 📁 Directorio"

        self.meta_label = QLabel(meta_text)
        self.meta_label.setStyleSheet(
            "font-size: 11px; color: rgba(255,255,255,0.5);"
        )
        name_box.addWidget(self.meta_label)

        header.addLayout(name_box)
        header.addStretch()

        # Estado
        self.status_label = QLabel(self._get_status_text())
        self.status_label.setStyleSheet(self._get_status_style())
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        header.addWidget(self.status_label)

        layout.addLayout(header)

        # === Descripción ===
        if self.info.get("description"):
            self.desc_label = QLabel(self.info["description"])
            self.desc_label.setStyleSheet(
                "font-size: 12px; color: rgba(255,255,255,0.7);"
            )
            self.desc_label.setWordWrap(True)
            layout.addWidget(self.desc_label)

        # === Capabilities ===
        caps = self.info.get("capabilities", [])
        if caps:
            caps_text = "🔒 " + ", ".join(caps)
            self.caps_label = QLabel(caps_text)
            self.caps_label.setStyleSheet(
                "font-size: 11px; color: rgba(77, 160, 196, 0.9);"
            )
            self.caps_label.setWordWrap(True)
            layout.addWidget(self.caps_label)

        # === Dependencias ===
        deps = self.info.get("dependencies", [])
        if deps:
            deps_text = "📦 Requiere: " + ", ".join(deps)
            self.deps_label = QLabel(deps_text)
            self.deps_label.setStyleSheet(
                "font-size: 11px; color: rgba(255, 152, 0, 0.9);"
            )
            layout.addWidget(self.deps_label)

        # === Botones ===
        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        buttons.addStretch()

        # Info
        info_btn = QPushButton("ℹ️ Info")
        info_btn.setFixedHeight(28)
        info_btn.setStyleSheet(self._get_btn_style("#4da0c4"))
        info_btn.clicked.connect(
            lambda: self.info_requested.emit(self.plugin_name)
        )
        buttons.addWidget(info_btn)

        # Configurar
        if self.info.get("is_enabled"):
            config_btn = QPushButton("⚙️ Configurar")
            config_btn.setFixedHeight(28)
            config_btn.setStyleSheet(self._get_btn_style("#8e24aa"))
            config_btn.clicked.connect(
                lambda: self.configure_requested.emit(self.plugin_name)
            )
            buttons.addWidget(config_btn)

        # Activar/Desactivar
        if self.info.get("is_failed"):
            pass
        elif self.info.get("is_enabled"):
            toggle_btn = QPushButton("⏸️ Desactivar")
            toggle_btn.setFixedHeight(28)
            toggle_btn.setStyleSheet(self._get_btn_style("#FF9800"))
            toggle_btn.clicked.connect(
                lambda: self.toggle_requested.emit(self.plugin_name, False)
            )
            buttons.addWidget(toggle_btn)
        else:
            toggle_btn = QPushButton("▶️ Activar")
            toggle_btn.setFixedHeight(28)
            toggle_btn.setStyleSheet(self._get_btn_style("#4CAF50"))
            toggle_btn.clicked.connect(
                lambda: self.toggle_requested.emit(self.plugin_name, True)
            )
            buttons.addWidget(toggle_btn)

        # Reload
        reload_btn = QPushButton("🔄")
        reload_btn.setFixedSize(28, 28)
        reload_btn.setToolTip("Recargar plugin")
        reload_btn.setStyleSheet(self._get_btn_style("#333"))
        reload_btn.clicked.connect(
            lambda: self.reload_requested.emit(self.plugin_name)
        )
        buttons.addWidget(reload_btn)

        # Desinstalar (solo si es ZIP)
        if self.info.get("origin") == "zip":
            uninstall_btn = QPushButton("🗑️")
            uninstall_btn.setFixedSize(28, 28)
            uninstall_btn.setToolTip("Desinstalar (borra archivos)")
            uninstall_btn.setStyleSheet(self._get_btn_style("#f44336"))
            uninstall_btn.clicked.connect(
                lambda: self.uninstall_requested.emit(self.plugin_name)
            )
            buttons.addWidget(uninstall_btn)

        layout.addLayout(buttons)

    def _get_icon(self) -> str:
        """Retorna el emoji del plugin."""
        icons = {
            "motion_detector": "🚶",
            "face_recognizer": "👤",
            "image_enhancer": "🎨",
            "document_scanner": "📄",
            "audio": "🎵",
            "notifications": "🔔",
            "debug_console": "🐛",
        }
        return icons.get(self.plugin_name, "🔌")

    def _get_status_text(self) -> str:
        if self.info.get("is_failed"):
            return "❌ FALLIDO"
        if self.info.get("is_enabled"):
            return "✅ ACTIVO"
        if self.info.get("is_loaded"):
            return "⏸️ INACTIVO"
        return "⏹️ DESCARGADO"

    def _get_status_style(self) -> str:
        if self.info.get("is_failed"):
            color = "#f44336"
        elif self.info.get("is_enabled"):
            color = "#4CAF50"
        elif self.info.get("is_loaded"):
            color = "#FF9800"
        else:
            color = "#888"

        return (
            f"color: {color}; font-size: 12px; "
            f"font-weight: bold; padding: 4px 12px; "
            f"background: rgba(0,0,0,0.3); border-radius: 12px;"
        )

    def _get_btn_style(self, bg: str) -> str:
        """Genera el estilo para un botón, normalizando colores hex."""
        # Normalizar hex a 6 dígitos
        def normalize_hex(hex_color: str) -> str:
            h = hex_color.lstrip("#")
            if len(h) == 3:
                h = "".join([c * 2 for c in h])
            return f"#{h}"

        def hex_to_rgb(hex_color: str):
            h = normalize_hex(hex_color).lstrip("#")
            try:
                return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
            except (ValueError, IndexError):
                return (51, 51, 51)

        bg_normalized = normalize_hex(bg)
        r, g, b = hex_to_rgb(bg_normalized)

        return f"""
            QPushButton {{
                background: {bg_normalized};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 4px 12px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: rgba({r}, {g}, {b}, 0.8);
            }}
        """

    def _apply_state_style(self):
        """Aplica el estilo según el estado."""
        if self.info.get("is_failed"):
            state = "failed"
        elif self.info.get("is_enabled"):
            state = "enabled"
        elif self.info.get("is_loaded"):
            state = "disabled"
        else:
            state = "unloaded"

        self.setProperty("state", state)
        self.style().unpolish(self)
        self.style().polish(self)