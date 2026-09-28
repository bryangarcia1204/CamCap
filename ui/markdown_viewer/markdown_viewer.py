"""
MarkdownViewer — Widget con QWebEngineView para renderizado nivel GitHub.

Features:
  - Renderizado completo vía marked.js
  - Resaltado de sintaxis vía highlight.js
  - Estilos GitHub Dark/Light
  - Búsqueda con Ctrl+F
  - Copiar bloques de código
  - Links externos abren en navegador del sistema
  - Anclas internas (#section) navegan dentro del documento
  - Zoom con Ctrl+/-/0
  - Auto-scroll al top al cargar nuevo contenido
"""
import os
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QUrl, Signal, QTimer, QSize
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QLabel, QSizePolicy, QApplication,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage
from PySide6.QtWebChannel import QWebChannel

from ui.markdown_viewer.markdown_bridge import MarkdownBridge
from utils.logger import get_logger

logger = get_logger("MarkdownViewer")


# ============================================================
# UTILIDADES
# ============================================================

def _get_assets_dir() -> Path:
    """
    Localiza el directorio de assets del viewer.

    Casos:
      1. Código fuente: <proyecto>/ui/markdown_viewer/assets/
      2. PyInstaller onefile: <sys._MEIPASS>/ui/markdown_viewer/assets/
      3. PyInstaller onedir: <exe_dir>/ui/markdown_viewer/assets/
    """
    if getattr(sys, "frozen", False):
        # PyInstaller
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        # Código fuente
        base = Path(__file__).parent

    assets = base / "assets"
    return assets


def _get_html_path() -> Path:
    """Localiza el HTML template."""
    return Path(__file__).parent / "markdown_viewer.html"


# ============================================================
# WEB PAGE CUSTOM (para interceptar navegación)
# ============================================================

class _MarkdownWebPage(QWebEnginePage):
    """
    QWebEnginePage custom que:
      - Bloquea la navegación fuera del HTML base.
      - Abre links externos en el navegador del sistema.
      - Permite anclas internas (#section).
    """

    link_clicked = Signal(str)

    def acceptNavigationRequest(self, url: QUrl, nav_type, is_main_frame: bool) -> bool:
        url_str = url.toString()

        # Permitir carga inicial del HTML local
        if nav_type == QWebEnginePage.NavigationType.NavigationTypeTyped:
            return True

        # Permitir file:// (carga del HTML y assets)
        if url_str.startswith("file://"):
            return True

        # Permitir anclas internas
        if url_str.startswith("about:blank#") or url_str.startswith("#"):
            return True

        # Permitir data: URIs (para imágenes inline)
        if url_str.startswith("data:"):
            return True

        # Links externos: abrir en navegador y bloquear navegación
        if url_str.startswith(("http://", "https://", "mailto:")):
            logger.debug(f"🌐 Abriendo link externo: {url_str}")
            QDesktopServices.openUrl(url)
            self.link_clicked.emit(url_str)
            return False

        # Bloquear todo lo demás
        return False


# ============================================================
# MARKDOWN VIEWER
# ============================================================

class MarkdownViewer(QWidget):
    """
    Visualizador de markdown con renderizado nivel GitHub.

    Uso:
        viewer = MarkdownViewer()
        viewer.load_markdown("# Hola\n\nEsto es **markdown**.")
        # o
        viewer.load_file("plugins/audio/README.md")
    """

    link_clicked = Signal(str)

    def __init__(self, parent=None, theme: str = "dark"):
        super().__init__(parent)
        self._theme = theme
        self._pending_markdown: Optional[str] = None
        self._html_ready = False
        self._current_file_path: Optional[str] = None

        self._setup_ui()
        self._setup_channel()
        self._load_html()
        self._setup_shortcuts()

    # ==================== UI ====================

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # === Toolbar de búsqueda ===
        toolbar = QWidget()
        toolbar.setObjectName("markdown_toolbar")
        toolbar.setStyleSheet("""
            QWidget#markdown_toolbar {
                background: rgba(255, 255, 255, 0.03);
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            }
        """)
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(8, 6, 8, 6)
        tb.setSpacing(6)

        search_icon = QLabel("🔍")
        search_icon.setStyleSheet("background: transparent; border: none;")
        tb.addWidget(search_icon)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Buscar en el README... (Ctrl+F)")
        self.search_edit.setFixedHeight(26)
        self.search_edit.setStyleSheet("""
            QLineEdit {
                background: rgba(0, 0, 0, 0.3);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 4px;
                padding: 2px 8px;
                color: white;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #4da0c4;
            }
        """)
        self.search_edit.returnPressed.connect(self._find_next)
        tb.addWidget(self.search_edit, 1)

        self._search_status = QLabel("")
        self._search_status.setStyleSheet(
            "color: rgba(255,255,255,0.5); font-size: 11px; "
            "background: transparent; border: none; padding: 0 8px;"
        )
        tb.addWidget(self._search_status)

        prev_btn = QPushButton("↑")
        prev_btn.setFixedSize(26, 26)
        prev_btn.setToolTip("Anterior (Shift+Enter)")
        prev_btn.clicked.connect(self._find_previous)
        prev_btn.setStyleSheet(self._toolbar_btn_style())
        tb.addWidget(prev_btn)

        next_btn = QPushButton("↓")
        next_btn.setFixedSize(26, 26)
        next_btn.setToolTip("Siguiente (Enter)")
        next_btn.clicked.connect(self._find_next)
        next_btn.setStyleSheet(self._toolbar_btn_style())
        tb.addWidget(next_btn)

        tb.addSpacing(6)

        zoom_out_btn = QPushButton("−")
        zoom_out_btn.setFixedSize(26, 26)
        zoom_out_btn.setToolTip("Reducir zoom (Ctrl+-)")
        zoom_out_btn.clicked.connect(self._zoom_out)
        zoom_out_btn.setStyleSheet(self._toolbar_btn_style())
        tb.addWidget(zoom_out_btn)

        self.zoom_label = QLabel("100%")
        self.zoom_label.setFixedWidth(45)
        self.zoom_label.setAlignment(Qt.AlignCenter)
        self.zoom_label.setStyleSheet(
            "color: #4da0c4; font-size: 11px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        tb.addWidget(self.zoom_label)

        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setFixedSize(26, 26)
        zoom_in_btn.setToolTip("Aumentar zoom (Ctrl++)")
        zoom_in_btn.clicked.connect(self._zoom_in)
        zoom_in_btn.setStyleSheet(self._toolbar_btn_style())
        tb.addWidget(zoom_in_btn)

        tb.addSpacing(6)

        copy_btn = QPushButton("📋 Copiar MD")
        copy_btn.setFixedHeight(26)
        copy_btn.setToolTip("Copiar el markdown crudo (Ctrl+Shift+C)")
        copy_btn.clicked.connect(self._copy_raw_markdown)
        copy_btn.setStyleSheet(self._toolbar_btn_style())
        tb.addWidget(copy_btn)

        layout.addWidget(toolbar)

        # === WebEngineView ===
        self.web_view = QWebEngineView()
        self.web_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Configuración de la página
        self.web_page = _MarkdownWebPage(self.web_view)
        self.web_page.link_clicked.connect(self._on_link_clicked)
        self.web_view.setPage(self.web_page)

        # Settings
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, True)

        # Fondo transparente para integrar con el tema
        self.web_page.setBackgroundColor(Qt.transparent)

        layout.addWidget(self.web_view, 1)

        self._zoom = 1.0

    def _toolbar_btn_style(self) -> str:
        return """
            QPushButton {
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 4px;
                color: white;
                font-size: 12px;
                padding: 0 8px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.12);
            }
            QPushButton:pressed {
                background: rgba(77, 160, 196, 0.3);
            }
        """

    # ==================== QWebChannel ====================

    def _setup_channel(self):
        """Configura el QWebChannel con el bridge."""
        self.bridge = MarkdownBridge(self)
        self.bridge.ready.connect(self._on_html_ready)
        self.bridge.linkClicked.connect(self._on_link_clicked)
        self.bridge.copyRequested.connect(self._on_copy_requested)

        self.channel = QWebChannel(self)
        self.channel.registerObject("bridge", self.bridge)

        # ⚠️ IMPORTANTE: mantener referencias a channel y bridge
        # como atributos para que no sean recolectadas por el GC.
        self.web_page.setWebChannel(self.channel)

    # ==================== CARGA DEL HTML ====================

    def _load_html(self):
        """Carga el HTML template con rutas relativas a assets."""
        html_path = _get_html_path()
        if not html_path.is_file():
            logger.error(f"❌ HTML template no encontrado: {html_path}")
            self._show_error_page(f"No se encontró: {html_path}")
            return

        # Cargar por URL local para que HTML pueda acceder a assets/
        url = QUrl.fromLocalFile(str(html_path.resolve()))
        self.web_view.load(url)
        logger.debug(f"📄 Cargando HTML: {url.toString()}")

    def _on_html_ready(self):
        """El JS notificó que está listo."""
        self._html_ready = True
        if self._pending_markdown is not None:
            self._set_markdown_js(self._pending_markdown)
            self._pending_markdown = None

    # ==================== API PÚBLICA ====================

    def load_markdown(self, markdown_text: str):
        """Carga markdown desde un string."""
        markdown_text = markdown_text or ""
        self._current_file_path = None

        if not self._html_ready:
            self._pending_markdown = markdown_text
            return

        self._set_markdown_js(markdown_text)
        self.bridge.set_base_url("")

    def load_file(self, path: str) -> bool:
        """
        Carga markdown desde archivo.

        Usa la ruta del archivo como base_url para resolver links e
        imágenes relativas.
        """
        try:
            p = Path(path)
            if not p.is_file():
                logger.warning(f"⚠️ Archivo no existe: {path}")
                self.load_markdown(f"*Archivo no encontrado: {path}*")
                return False

            content = p.read_text(encoding="utf-8")
            self._current_file_path = str(p.resolve())

            if not self._html_ready:
                self._pending_markdown = content
            else:
                self._set_markdown_js(content)

            # Base URL: la carpeta del archivo, para resolver imágenes relativas
            base = QUrl.fromLocalFile(str(p.parent.resolve()) + "/").toString()
            self.bridge.set_base_url(base)

            logger.debug(f"📄 Cargado: {path} ({len(content)} chars)")
            return True

        except Exception as e:
            logger.error(f"❌ Error leyendo {path}: {e}", exc_info=True)
            self.load_markdown(f"**Error leyendo archivo:**\n\n```\n{e}\n```")
            return False

    def clear(self):
        """Limpia el viewer."""
        self._pending_markdown = ""
        self._current_file_path = None
        if self._html_ready:
            self._set_markdown_js("")
        self.search_edit.clear()
        self._search_status.setText("")

    def get_raw_markdown(self) -> str:
        """Retorna el markdown crudo."""
        return self.bridge.text

    def set_theme(self, theme: str):
        """Cambia el tema: 'dark' o 'light'."""
        self._theme = theme
        self.bridge.set_theme(theme)

    def scroll_to_top(self):
        """Scroll al inicio del documento."""
        if self._html_ready:
            self.web_view.page().runJavaScript("window.scrollTo(0, 0);")

    # ==================== JS INTEROP ====================

    def _set_markdown_js(self, markdown_text: str):
        """Pasa el markdown al JS vía el bridge."""
        # Escapar para que no rompa el JS si se pasara inline.
        # Pero con QWebChannel no hace falta: el bridge lo maneja como string.
        self.bridge.set_text(markdown_text)

    def _run_js(self, js_code: str):
        """Ejecuta JavaScript en la página."""
        if not self._html_ready:
            return
        self.web_view.page().runJavaScript(js_code)

    # ==================== BÚSQUEDA ====================

    def _find_next(self):
        text = self.search_edit.text()
        if not text:
            return
        # Usar la API de búsqueda de QWebEngine
        flags = QWebEnginePage.FindFlag(0) if hasattr(QWebEnginePage, "FindFlag") else None
        self._find_text(text, backward=False)

    def _find_previous(self):
        text = self.search_edit.text()
        if not text:
            return
        self._find_text(text, backward=True)

    def _find_text(self, text: str, backward: bool):
        """Búsqueda nativa de QWebEngine."""
        try:
            # QWebEnginePage.findText(text, flags, callback)
            flags = QWebEnginePage.FindFlag(0)
            # Nota: en PySide6, QWebEnginePage.FindFlag puede no existir;
            # usamos la firma simple.
            self.web_page.findText(text, QWebEnginePage.FindFlag(0),
                                    self._on_find_result)
        except Exception:
            # Fallback: búsqueda vía JS
            escaped = text.replace("\\", "\\\\").replace("'", "\\'")
            self._run_js(f"window.find('{escaped}', false, {str(backward).lower()});")

    def _on_find_result(self, found: bool):
        """Callback de la búsqueda."""
        if found:
            self._search_status.setText("✓")
        else:
            self._search_status.setText("✗")

    # ==================== ZOOM ====================

    def _zoom_in(self):
        self._zoom = min(3.0, self._zoom * 1.1)
        self._apply_zoom()

    def _zoom_out(self):
        self._zoom = max(0.5, self._zoom / 1.1)
        self._apply_zoom()

    def _zoom_reset(self):
        self._zoom = 1.0
        self._apply_zoom()

    def _apply_zoom(self):
        """Aplica el zoom vía setZoomFactor."""
        try:
            self.web_view.setZoomFactor(self._zoom)
            self.zoom_label.setText(f"{int(self._zoom * 100)}%")
        except Exception as e:
            logger.debug(f"Error aplicando zoom: {e}")

    # ==================== COPIAR ====================

    def _copy_raw_markdown(self):
        """Copia el markdown crudo al portapapeles."""
        try:
            clipboard = QApplication.clipboard()
            clipboard.setText(self.bridge.text)
            logger.debug("📋 Markdown copiado al portapapeles")
        except Exception as e:
            logger.debug(f"Error copiando: {e}")

    def _on_copy_requested(self, text: str):
        """El JS pide copiar un texto específico (ej. bloque de código)."""
        try:
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            logger.debug(f"📋 Copiado desde JS: {len(text)} chars")
        except Exception as e:
            logger.debug(f"Error copiando desde JS: {e}")

    # ==================== LINKS ====================

    def _on_link_clicked(self, url: str):
        """Propaga el link clickeado."""
        self.link_clicked.emit(url)

    # ==================== SHORTCUTS ====================

    def _setup_shortcuts(self):
        """Configura atajos de teclado."""
        # Ctrl+F → foco en búsqueda
        sc_find = QShortcut(QKeySequence("Ctrl+F"), self)
        sc_find.activated.connect(self._focus_search)

        # Ctrl+= / Ctrl++ → zoom in
        sc_zoom_in = QShortcut(QKeySequence("Ctrl+="), self)
        sc_zoom_in.activated.connect(self._zoom_in)
        sc_zoom_in2 = QShortcut(QKeySequence("Ctrl++"), self)
        sc_zoom_in2.activated.connect(self._zoom_in)

        # Ctrl+- → zoom out
        sc_zoom_out = QShortcut(QKeySequence("Ctrl+-"), self)
        sc_zoom_out.activated.connect(self._zoom_out)

        # Ctrl+0 → zoom reset
        sc_zoom_reset = QShortcut(QKeySequence("Ctrl+0"), self)
        sc_zoom_reset.activated.connect(self._zoom_reset)

        # Ctrl+Shift+C → copiar markdown
        sc_copy = QShortcut(QKeySequence("Ctrl+Shift+C"), self)
        sc_copy.activated.connect(self._copy_raw_markdown)

        # Escape → limpiar búsqueda
        sc_esc = QShortcut(QKeySequence("Escape"), self)
        sc_esc.activated.connect(self._clear_search)

    def _focus_search(self):
        """Enfoca el campo de búsqueda."""
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    def _clear_search(self):
        """Limpia la búsqueda."""
        self.search_edit.clear()
        self._search_status.setText("")

    # ==================== ERROR ====================

    def _show_error_page(self, message: str):
        """Muestra una página de error."""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8">
        <style>
            body {{
                background: #0d1117;
                color: #f85149;
                font-family: -apple-system, sans-serif;
                padding: 40px;
                text-align: center;
            }}
        </style>
        </head>
        <body>
            <h2>⚠️ Error cargando el viewer</h2>
            <p>{message}</p>
        </body>
        </html>
        """
        self.web_view.setHtml(html, QUrl("about:blank"))