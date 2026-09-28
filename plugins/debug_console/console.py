"""
Consola de debug integrada.

Solo se activa en modo debug. Muestra los logs en tiempo real
recibidos vía QtLogHandler.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QPushButton, QLabel, QCheckBox, QComboBox,
)
from PySide6.QtGui import QTextCursor, QFont, QColor, QTextCharFormat
from PySide6.QtCore import Qt, Slot

from utils.logger import get_logger, get_debug_console_handler

logger = get_logger("DebugConsole")


# Colores por nivel de log
LEVEL_COLORS = {
    10: "#808080",   # DEBUG - gris
    20: "#d4d4d4",   # INFO - blanco apagado
    30: "#ffcc00",   # WARNING - amarillo
    40: "#ff5555",   # ERROR - rojo
    50: "#ff2222",   # CRITICAL - rojo intenso
}

LEVEL_NAMES = {
    10: "DEBUG",
    20: "INFO",
    30: "WARNING",
    40: "ERROR",
    50: "CRITICAL",
}


class DebugConsole(QWidget):
    """
    Consola de debug con:
    - Muestra los logs en tiempo real
    - Filtro por nivel
    - Botón de limpiar
    - Auto-scroll configurable
    - Límite de líneas configurable
    """

    DEFAULT_MAX_LINES = 5000

    def __init__(self, parent=None):
        super().__init__(parent)

        # Estado
        self._auto_scroll = True
        self._min_level = 10   # DEBUG por defecto
        self._max_lines = self.DEFAULT_MAX_LINES
        self._connected_to_logger = False

        self._setup_ui()
        self._connect_logger()

        logger.debug("🖥️ DebugConsole inicializada")

    # ==================== SETUP ====================

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # === Toolbar ===
        toolbar = QWidget()
        toolbar.setStyleSheet("""
            QWidget {
                background: #1a1a2e;
                border-bottom: 1px solid rgba(255,255,255,0.1);
            }
        """)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(8, 4, 8, 4)
        toolbar_layout.setSpacing(6)

        title = QLabel("🖥️ Consola de Debug")
        title.setStyleSheet(
            "color: #4da0c4; font-weight: bold; font-size: 12px;"
        )
        toolbar_layout.addWidget(title)

        toolbar_layout.addSpacing(12)

        # Filtro por nivel
        filter_label = QLabel("Nivel:")
        filter_label.setStyleSheet("color: #aaa; font-size: 11px;")
        toolbar_layout.addWidget(filter_label)

        self.level_combo = QComboBox()
        self.level_combo.addItem("Todos", 10)
        self.level_combo.addItem("INFO", 20)
        self.level_combo.addItem("WARNING", 30)
        self.level_combo.addItem("ERROR", 40)
        self.level_combo.addItem("CRITICAL", 50)
        self.level_combo.setFixedWidth(100)
        self.level_combo.currentIndexChanged.connect(self._on_level_changed)
        self.level_combo.setStyleSheet("""
            QComboBox {
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 4px;
                padding: 2px 6px;
                color: white;
                font-size: 11px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background: #1a237e;
                color: white;
                selection-background-color: #4a148c;
            }
        """)
        toolbar_layout.addWidget(self.level_combo)

        toolbar_layout.addSpacing(8)

        # Auto-scroll
        self.autoscroll_cb = QCheckBox("Auto-scroll")
        self.autoscroll_cb.setChecked(True)
        self.autoscroll_cb.setStyleSheet("color: #aaa; font-size: 11px;")
        self.autoscroll_cb.stateChanged.connect(self._on_autoscroll_changed)
        toolbar_layout.addWidget(self.autoscroll_cb)

        toolbar_layout.addStretch()

        # Contador de líneas
        self.count_label = QLabel("0 líneas")
        self.count_label.setStyleSheet("color: #666; font-size: 11px;")
        toolbar_layout.addWidget(self.count_label)

        toolbar_layout.addSpacing(8)

        # Botón limpiar
        self.clear_btn = QPushButton("🗑️ Limpiar")
        self.clear_btn.setFixedHeight(24)
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background: rgba(244, 67, 54, 0.2);
                border: 1px solid rgba(244, 67, 54, 0.4);
                border-radius: 4px;
                color: #ff8888;
                font-size: 11px;
                padding: 2px 10px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: rgba(244, 67, 54, 0.35);
                border-color: #f44336;
                color: white;
            }
        """)
        self.clear_btn.clicked.connect(self.clear)
        toolbar_layout.addWidget(self.clear_btn)

        layout.addWidget(toolbar)

        # === TextEdit ===
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setLineWrapMode(QTextEdit.NoWrap)
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background: #0d0d1a;
                color: #d4d4d4;
                border: none;
                padding: 4px;
                font-family: "Consolas", "Monaco", "Courier New", monospace;
                font-size: 11px;
                selection-background-color: #4da0c4;
            }
        """)

        font = QFont("Consolas", 9)
        font.setStyleHint(QFont.Monospace)
        self.text_edit.setFont(font)

        layout.addWidget(self.text_edit)

    def _connect_logger(self):
        """Conecta el handler del logger a la consola."""
        if self._connected_to_logger:
            return
        try:
            handler = get_debug_console_handler()
            handler.emitter.message_logged.connect(
                self._on_log_message, Qt.QueuedConnection
            )
            self._connected_to_logger = True
            logger.debug("🖥️ DebugConsole conectada al logger")
        except Exception as e:
            logger.error(f"❌ No se pudo conectar DebugConsole al logger: {e}")

    def _disconnect_logger(self):
        """Desconecta del handler del logger."""
        if not self._connected_to_logger:
            return
        try:
            handler = get_debug_console_handler()
            handler.emitter.message_logged.disconnect(self._on_log_message)
        except Exception:
            pass
        self._connected_to_logger = False

    # ==================== CONFIG ====================

    def set_max_lines(self, max_lines: int):
        """Configura el límite de líneas."""
        self._max_lines = max(100, int(max_lines))
        # Recortar si ya hay más
        self._enforce_max_lines()
        logger.debug(f"🖥️ max_lines = {self._max_lines}")

    def set_auto_scroll(self, enabled: bool):
        """Configura el auto-scroll."""
        self._auto_scroll = bool(enabled)
        self.autoscroll_cb.blockSignals(True)
        self.autoscroll_cb.setChecked(self._auto_scroll)
        self.autoscroll_cb.blockSignals(False)
        logger.debug(f"🖥️ auto_scroll = {self._auto_scroll}")

    def get_max_lines(self) -> int:
        return self._max_lines

    def is_auto_scroll(self) -> bool:
        return self._auto_scroll

    # ==================== SLOTS ====================

    @Slot(str, int)
    def _on_log_message(self, message: str, level: int):
        """Recibe un mensaje del logger y lo añade al QTextEdit."""
        # Filtrar por nivel
        if level < self._min_level:
            return

        # Color según nivel
        color = LEVEL_COLORS.get(level, "#d4d4d4")

        # Añadir con formato
        cursor = self.text_edit.textCursor()
        cursor.movePosition(QTextCursor.End)

        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))

        cursor.insertText(message + "\n", fmt)

        # Limitar líneas
        self._enforce_max_lines()

        # Auto-scroll
        if self._auto_scroll:
            self.text_edit.verticalScrollBar().setValue(
                self.text_edit.verticalScrollBar().maximum()
            )

        # Actualizar contador
        self._update_count()

    def _enforce_max_lines(self):
        """Recorta el documento si supera el máximo."""
        doc = self.text_edit.document()
        if doc.blockCount() <= self._max_lines:
            return
        cursor = self.text_edit.textCursor()
        cursor.movePosition(QTextCursor.Start)
        cursor.movePosition(
            QTextCursor.Down,
            QTextCursor.KeepAnchor,
            doc.blockCount() - self._max_lines,
        )
        cursor.removeSelectedText()

    def _update_count(self):
        self.count_label.setText(
            f"{self.text_edit.document().blockCount()} líneas"
        )

    def _on_level_changed(self, index: int):
        self._min_level = self.level_combo.itemData(index)

    def _on_autoscroll_changed(self, state: int):
        self._auto_scroll = (state == 2)

    # ==================== API PÚBLICA ====================

    def clear(self):
        """Limpia la consola."""
        self.text_edit.clear()
        self.count_label.setText("0 líneas")
        logger.debug("🗑️ Consola limpiada")

    def append(self, text: str, color: str = None):
        """Añade texto manualmente."""
        cursor = self.text_edit.textCursor()
        cursor.movePosition(QTextCursor.End)

        fmt = QTextCharFormat()
        if color:
            fmt.setForeground(QColor(color))

        cursor.insertText(text + "\n", fmt)

        if self._auto_scroll:
            self.text_edit.verticalScrollBar().setValue(
                self.text_edit.verticalScrollBar().maximum()
            )

        self._update_count()

    def cleanup(self):
        """Limpia recursos al destruir el widget."""
        self._disconnect_logger()