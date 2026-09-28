"""
Puente QWebChannel entre Python y el HTML del markdown viewer.

Expone propiedades que el JS puede leer y escuchar:
  - text: markdown crudo
  - theme: 'dark' | 'light'
  - base_url: URL base para resolver links/imágenes relativas
  - py_click: señal cuando el usuario hace click en un link
"""
from PySide6.QtCore import QObject, Signal, Property, Slot, QUrl
from utils.logger import get_logger

logger = get_logger("MarkdownBridge")


class MarkdownBridge(QObject):
    """
    Objeto puente registrado en QWebChannel como 'bridge'.

    El JS accede a él vía:
        new QWebChannel(qt.webChannelTransport, function(channel) {
            var bridge = channel.objects.bridge;
            bridge.textChanged.connect(function(text) { ... });
            bridge.py_click.connect(function(url) { ... });
        });
    """

    # Propiedades notificables
    textChanged = Signal(str)
    themeChanged = Signal(str)
    baseUrlChanged = Signal(str)

    # Slots llamables desde JS
    linkClicked = Signal(str)          # JS → Python: usuario clickeó un link
    copyRequested = Signal(str)        # JS → Python: copiar texto
    ready = Signal()                   # JS → Python: página lista

    def __init__(self, parent=None):
        super().__init__(parent)
        self._text: str = ""
        self._theme: str = "dark"
        self._base_url: str = ""

    # ==================== PROPIEDADES ====================

    @Property(str, notify=textChanged)
    def text(self) -> str:
        return self._text

    def set_text(self, value: str):
        value = value or ""
        if value != self._text:
            self._text = value
            self.textChanged.emit(value)
            logger.debug(f"📝 Markdown actualizado ({len(value)} chars)")

    @Property(str, notify=themeChanged)
    def theme(self) -> str:
        return self._theme

    def set_theme(self, value: str):
        value = value or "dark"
        if value != self._theme:
            self._theme = value
            self.themeChanged.emit(value)
            logger.debug(f"🎨 Tema cambiado: {value}")

    @Property(str, notify=baseUrlChanged)
    def baseUrl(self) -> str:
        return self._base_url

    def set_base_url(self, value: str):
        value = value or ""
        if value != self._base_url:
            self._base_url = value
            self.baseUrlChanged.emit(value)

    # ==================== SLOTS (llamados desde JS) ====================

    @Slot(str)
    def onLinkClicked(self, url: str):
        """El JS llama a esto cuando el usuario clickea un link."""
        logger.debug(f"🔗 Link clickeado: {url}")
        self.linkClicked.emit(url)

    @Slot(str)
    def onCopyRequested(self, text: str):
        """El JS pide copiar texto al portapapeles."""
        self.copyRequested.emit(text)

    @Slot()
    def onReady(self):
        """El JS notifica que la página está lista."""
        logger.debug("✅ Markdown viewer HTML listo")
        self.ready.emit()