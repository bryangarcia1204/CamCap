"""
Diálogo principal del Plugin Manager (GUI).
"""
import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QScrollArea, QWidget, QMessageBox,
    QFrame, QCheckBox, QSplitter
)
from PySide6.QtCore import Qt, Signal

from ui.plugin_card import PluginCard
from ui.plugin_info_dialog import PluginInfoDialog
from ui.plugin_install_dialog import PluginInstallDialog
from core.plugin_api import get_plugin_manager
from utils.logger import get_logger

logger = get_logger("PluginManagerDialog")


class PluginManagerDialog(QDialog):
    """Diálogo de administración de plugins."""

    plugins_changed = Signal()   # Emitido cuando cambia algo (activar/desactivar/instalar)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pm = get_plugin_manager()
        self._cards = {}   # plugin_name → PluginCard

        self.setWindowTitle("🔌 Administrador de Plugins")
        self.setMinimumSize(1000, 700)
        self.setModal(True)
        self._setup_ui()
        self._load_plugins()

    # ==================== UI ====================

    def _setup_ui(self):
        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0d1445, stop:1 #2a0a4a);
            }
            QLabel { color: white; }
            QLineEdit, QComboBox {
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 8px;
                padding: 6px 12px;
                color: white;
                font-size: 12px;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #4da0c4;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1a237e, stop:1 #4a148c);
                color: white;
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #283593, stop:1 #6a1b9a);
            }
            QPushButton[type="success"] {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2e7d32, stop:1 #43a047);
            }
            QPushButton[type="secondary"] {
                background: rgba(255,255,255,0.08);
            }
            QPushButton[type="secondary"]:hover {
                background: rgba(255,255,255,0.15);
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                background: rgba(255,255,255,0.04);
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: rgba(77,160,196,0.5);
                border-radius: 5px;
                min-height: 30px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # === Header ===
        header = QHBoxLayout()

        title = QLabel("🔌 Administrador de Plugins")
        title.setStyleSheet(
            "font-size: 22px; font-weight: bold; color: #4da0c4;"
        )
        header.addWidget(title)
        header.addStretch()

        # Refresh
        refresh_btn = QPushButton("🔄 Refrescar")
        refresh_btn.setProperty("type", "secondary")
        refresh_btn.clicked.connect(self._load_plugins)
        header.addWidget(refresh_btn)

        # Instalar
        install_btn = QPushButton("📦 Instalar ZIP")
        install_btn.setProperty("type", "success")
        install_btn.clicked.connect(self._install_plugin)
        header.addWidget(install_btn)

        layout.addLayout(header)

        # === Barra de filtros ===
        filters = QHBoxLayout()
        filters.setSpacing(10)

        # Buscar
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍 Buscar por nombre, descripción...")
        self.search_edit.textChanged.connect(self._apply_filters)
        filters.addWidget(self.search_edit, 2)

        # Estado
        filters.addWidget(QLabel("Estado:"))
        self.state_combo = QComboBox()
        self.state_combo.addItems([
            "Todos", "✅ Activos", "⏸️ Inactivos",
            "❌ Fallidos", "⏹️ Descargados",
        ])
        self.state_combo.currentTextChanged.connect(self._apply_filters)
        filters.addWidget(self.state_combo)

        # Origen
        filters.addWidget(QLabel("Origen:"))
        self.origin_combo = QComboBox()
        self.origin_combo.addItems([
            "Todos", "📁 Directorio", "📦 ZIP",
        ])
        self.origin_combo.currentTextChanged.connect(self._apply_filters)
        filters.addWidget(self.origin_combo)

        layout.addLayout(filters)

        # === Lista (scroll) ===
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)

        self.list_widget = QWidget()
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setSpacing(10)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.addStretch()

        self.scroll.setWidget(self.list_widget)
        layout.addWidget(self.scroll, 1)

        # === Footer (stats) ===
        self.stats_label = QLabel("Cargando...")
        self.stats_label.setStyleSheet(
            "color: rgba(255,255,255,0.6); "
            "font-size: 12px; padding: 8px; "
            "background: rgba(0,0,0,0.2); border-radius: 6px;"
        )
        layout.addWidget(self.stats_label)

        # ✅ NUEVO: Label de status (feedback de acciones)
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            "color: #4CAF50; "
            "font-size: 12px; padding: 4px;"
        )
        self.status_label.setVisible(False)   # oculto por defecto
        layout.addWidget(self.status_label)

        # === Botones inferiores ===
        bottom = QHBoxLayout()
        bottom.addStretch()

        close_btn = QPushButton("Cerrar")
        close_btn.setProperty("type", "secondary")
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(close_btn)

        layout.addLayout(bottom)

    def _show_status(self, message: str, timeout_ms: int = 3000):
        """Muestra un mensaje temporal en el status label."""
        self.status_label.setText(message)
        self.status_label.setVisible(True)
        
        from utils.timer_manager import timer_manager
        timer_manager.create("show_status", timeout_ms, 
                             callback= lambda: self.status_label.setVisible(False), single_shot=True, start=True)

    # ==================== CARGA ====================

    def _load_plugins(self):
        """Carga y muestra todos los plugins."""
        # Limpiar
        self._clear_list()
        self._cards = {}

        if self.pm is None:
            self._show_empty("⚠️ PluginManager no disponible")
            return

        try:
            plugins_info = self.pm.get_all_plugin_info()
        except Exception as e:
            logger.error(f"Error cargando plugins: {e}", exc_info=True)
            self._show_empty(f"⚠️ Error: {e}")
            return

        if not plugins_info:
            self._show_empty("📭 No hay plugins instalados")
            return

        # Ordenar: activos primero, luego por nombre
        plugins_info.sort(
            key=lambda x: (
                not x.get("is_enabled", False),
                not x.get("is_loaded", False),
                x.get("name", ""),
            )
        )

        # Crear cards
        for info in plugins_info:
            card = PluginCard(info)
            card.configure_requested.connect(self._on_configure)
            card.toggle_requested.connect(self._on_toggle)
            card.info_requested.connect(self._on_info)
            card.uninstall_requested.connect(self._on_uninstall)
            card.reload_requested.connect(self._on_reload)

            # Insertar antes del stretch
            self.list_layout.insertWidget(
                self.list_layout.count() - 1, card
            )
            self._cards[info["name"]] = card

        self._update_stats()
        self._apply_filters()

    def _clear_list(self):
        """Limpia todos los widgets de la lista."""
        while self.list_layout.count() > 1:  # mantener el stretch
            item = self.list_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

    def _show_empty(self, message: str):
        """Muestra un mensaje de lista vacía."""
        empty = QLabel(message)
        empty.setAlignment(Qt.AlignCenter)
        empty.setStyleSheet(
            "color: rgba(255,255,255,0.5); "
            "font-size: 14px; font-style: italic; padding: 40px;"
        )
        self.list_layout.insertWidget(0, empty)

    def _update_stats(self):
        """Actualiza el footer con stats."""
        if self.pm is None:
            return
        try:
            stats = self.pm.get_stats()
            self.stats_label.setText(
                f"📊 Total: {stats['total']} plugins  ·  "
                f"✅ Activos: {stats['enabled']}  ·  "
                f"⏸️ Inactivos: {stats['loaded'] - stats['enabled']}  ·  "
                f"⏹️ Descargados: {stats['total'] - stats['loaded']}  ·  "
                f"❌ Fallidos: {stats['failed']}"
            )
        except Exception as e:
            self.stats_label.setText(f"Error: {e}")

    # ==================== FILTROS ====================

    def _apply_filters(self):
        """Aplica los filtros de búsqueda/estado/origen."""
        search = self.search_edit.text().lower().strip()
        state = self.state_combo.currentText()
        origin = self.origin_combo.currentText()

        for name, card in self._cards.items():
            info = card.info

            # Búsqueda
            if search:
                text = (
                    info.get("name", "") + " " +
                    info.get("description", "") + " " +
                    info.get("author", "")
                ).lower()
                if search not in text:
                    card.setVisible(False)
                    continue

            # Estado
            if state != "Todos":
                if state == "✅ Activos" and not info.get("is_enabled"):
                    card.setVisible(False); continue
                if state == "⏸️ Inactivos" and not (
                    info.get("is_loaded") and not info.get("is_enabled")
                ):
                    card.setVisible(False); continue
                if state == "❌ Fallidos" and not info.get("is_failed"):
                    card.setVisible(False); continue
                if state == "⏹️ Descargados" and info.get("is_loaded"):
                    card.setVisible(False); continue

            # Origen
            if origin != "Todos":
                if origin == "📁 Directorio" and info.get("origin") != "directory":
                    card.setVisible(False); continue
                if origin == "📦 ZIP" and info.get("origin") != "zip":
                    card.setVisible(False); continue

            card.setVisible(True)

    # ==================== ACCIONES ====================

    def _on_configure(self, plugin_name: str):
        """Abre la configuración de un plugin."""
        # Cerrar este diálogo y abrir SettingsDialog en la tab del plugin
        self.plugins_changed.emit()
        self.accept()

        # Notificar al MainWindow que abra SettingsDialog
        parent = self.parent()
        if parent and hasattr(parent, '_open_plugin_config_tab'):
            parent._open_plugin_config_tab(plugin_name)

    def _on_toggle(self, plugin_name: str, enable: bool):
        """Activa/desactiva un plugin."""
        if self.pm is None:
            return

        try:
            if enable:
                success = self.pm.enable(plugin_name)
                msg = "activado" if success else "no se pudo activar"
            else:
                success = self.pm.disable(plugin_name)
                msg = "desactivado" if success else "no se pudo desactivar"

            if success:
                logger.info(f"🔌 Plugin '{plugin_name}' {msg}")
                self._show_status(f"✅ Plugin '{plugin_name}' {msg}")
            else:
                QMessageBox.warning(
                    self, "Error",
                    f"No se pudo {'activar' if enable else 'desactivar'} "
                    f"'{plugin_name}'"
                )
        except Exception as e:
            logger.error(f"Error toggling plugin: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", str(e))

        # Refrescar lista
        self._load_plugins()
        self.plugins_changed.emit()

    def _on_info(self, plugin_name: str):
        """Muestra info detallada."""
        if self.pm is None:
            return
        info = self.pm.get_plugin_info(plugin_name)
        if info is None:
            QMessageBox.warning(self, "Error", "Plugin no encontrado")
            return

        dialog = PluginInfoDialog(info, self)
        dialog.exec()

    def _on_uninstall(self, plugin_name: str):
        """Desinstala un plugin."""
        if self.pm is None:
            return

        reply = QMessageBox.question(
            self,
            "Confirmar desinstalación",
            f"¿Desinstalar '{plugin_name}'?\n\n"
            f"Se eliminarán los archivos del plugin y el ZIP original.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            ok, msg = self.pm.uninstall(plugin_name)
            if ok:
                QMessageBox.information(self, "Desinstalado", msg)
                logger.info(f"🗑️ {msg}")
            else:
                QMessageBox.warning(self, "Error", msg)
        except Exception as e:
            logger.error(f"Error desinstalando: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", str(e))

        self._load_plugins()
        self.plugins_changed.emit()

    def _on_reload(self, plugin_name: str):
        """Recarga un plugin."""
        if self.pm is None:
            return

        try:
            ok, msg = self.pm.reload_plugin(plugin_name)
            if ok:
                self._show_status(f"✅ {msg}")
                logger.info(msg)
            else:
                QMessageBox.warning(self, "Error", msg)
        except Exception as e:
            logger.error(f"Error recargando: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", str(e))

        self._load_plugins()
        self.plugins_changed.emit()

    def _install_plugin(self):
        """Abre el diálogo de instalación."""
        if self.pm is None:
            return

        dialog = PluginInstallDialog(self.pm, self)
        if dialog.exec() == QDialog.Accepted:
            if dialog.installed_plugin_name:
                # Cargar y activar automáticamente
                try:
                    self.pm.load(dialog.installed_plugin_name)
                    self.pm.enable(dialog.installed_plugin_name)
                except Exception as e:
                    logger.error(f"Error activando plugin instalado: {e}")

                self._show_status(
                    f"✅ Plugin '{dialog.installed_plugin_name}' instalado"
                )

                self._load_plugins()
                self.plugins_changed.emit()