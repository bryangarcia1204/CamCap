"""
Plugin: Escáner de Documentos.

Depende de: image_enhancer.
Registra provider + analyzer + ConfigTab.
"""
from core.plugin_api import BasePlugin
from utils.logger import get_logger

logger = get_logger("Plugin.DocumentScanner")


class DocumentScannerPlugin(BasePlugin):
    NAME = "document_scanner"
    VERSION = "1.0.0"
    DESCRIPTION = "Escaneo de documentos con OCR (Tesseract)"
    AUTHOR = "ProCamera"
    DEPENDENCIES = ["image_enhancer"]
    REQUIRES_DEBUG = False

    def __init__(self, context):
        super().__init__(context)
        self._scanner_class = None
        self._tab_provider = None
        self._analyzer = None

    def on_load(self) -> bool:
        try:
            from plugins.document_scanner.scan_manager import ScanManager
            self._scanner_class = ScanManager
            logger.info("🔌 DocumentScannerPlugin: clase cargada")
            return True
        except Exception as e:
            logger.error(f"❌ Error cargando ScanManager: {e}", exc_info=True)
            return False

    def on_enable(self) -> bool:
        try:
            from core.extensions.interfaces import DocumentScannerProvider
            self.register_extension(DocumentScannerProvider, self, priority=50)

            from plugins.document_scanner.analyzer import DocumentAnalyzer
            from core.extensions.interfaces import FrameAnalyzer
            self._analyzer = DocumentAnalyzer(self.context)
            self.register_extension(
                FrameAnalyzer, self._analyzer,
                priority=130, metadata={"feature": "scan"},
            )
            logger.debug("🎯 DocumentAnalyzer registrado en ExtensionRegistry")

            from core.extensions.interfaces import ConfigTab
            from core.extensions.config_tab_provider import PluginConfigTabProvider
            from plugins.document_scanner.config_tab import DocumentScannerConfigTab
            self._tab_provider = PluginConfigTabProvider(
                plugin_name=self.NAME,
                plugin_context=self.context,
                tab_class=DocumentScannerConfigTab,
                tab_id="plugin_document_scanner",
                title="Document Scanner",
                icon="📄",
            )
            self.register_extension(ConfigTab, self._tab_provider, priority=130)

            logger.info("✅ DocumentScannerPlugin activado (provider + analyzer + ConfigTab)")
            return True
        except Exception as e:
            logger.error(f"❌ Error activando: {e}", exc_info=True)
            return False

    def on_disable(self):
        if self._analyzer is not None:
            try:
                from core.extension_registry import get_extension_registry
                from core.extensions.interfaces import FrameAnalyzer
                registry = get_extension_registry()
                registry.unregister(FrameAnalyzer, self._analyzer)
                self._analyzer.cleanup()
                self._analyzer = None
            except Exception as e:
                logger.error(f"Error desregistrando DocumentAnalyzer: {e}", exc_info=True)

        if self._tab_provider is not None:
            try:
                from core.extension_registry import get_extension_registry
                from core.extensions.interfaces import ConfigTab
                registry = get_extension_registry()
                registry.unregister(ConfigTab, self._tab_provider)
                self._tab_provider.cleanup()
                self._tab_provider = None
            except Exception as e:
                logger.error(f"Error desregistrando ConfigTab: {e}", exc_info=True)

        logger.info("⏸️ DocumentScannerPlugin desactivado")

    def on_unload(self):
        self._scanner_class = None
        self._tab_provider = None
        self._analyzer = None
        logger.info("🔌 DocumentScannerPlugin descargado")

    def create_scanner(self, tesseract_path=None):
        if self._scanner_class is None:
            from plugins.document_scanner.scan_manager import ScanManager
            self._scanner_class = ScanManager
        return self._scanner_class(tesseract_path=tesseract_path)

    def get_class(self):
        return self._scanner_class

    def get_analyzer(self):
        return self._analyzer