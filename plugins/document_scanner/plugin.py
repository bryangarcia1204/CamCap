"""
Plugin: Escáner de Documentos.

Se suscribe a:
  - IMAGE_SAVED       → aplica OCR y guarda el .txt al lado
  - SETTINGS_CHANGED  → recarga config
  - APP_CLOSING       → limpia

Registra:
  - FrameAnalyzer (para detección en vivo de documentos)
  - ConfigTab
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
            # 1. FrameAnalyzer (detección en vivo)
            from plugins.document_scanner.analyzer import DocumentAnalyzer
            from core.extensions.interfaces import FrameAnalyzer

            self._analyzer = DocumentAnalyzer(self.context)
            self.register_extension(
                FrameAnalyzer, self._analyzer,
                priority=130, metadata={"feature": "scan"},
            )

            # 2. ConfigTab
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

            # 3. Suscribirse a IMAGE_SAVED para OCR post-captura
            if self.context.event_bus is not None:
                from core.events import IMAGE_SAVED, SETTINGS_CHANGED, APP_CLOSING
                bus = self.context.event_bus
                bus.subscribe(IMAGE_SAVED, self._on_image_saved, owner=self.NAME)
                bus.subscribe(SETTINGS_CHANGED, self._on_settings, owner=self.NAME)
                bus.subscribe(APP_CLOSING, self._on_app_closing, owner=self.NAME)
                logger.debug("🔗 DocumentScanner suscrito a IMAGE_SAVED")

            logger.info("✅ DocumentScannerPlugin activado (analyzer + ConfigTab + eventos)")
            return True
        except Exception as e:
            logger.error(f"❌ Error activando: {e}", exc_info=True)
            return False

    def on_disable(self):
        if self.context.event_bus is not None:
            from core.events import IMAGE_SAVED, SETTINGS_CHANGED, APP_CLOSING
            bus = self.context.event_bus
            bus.unsubscribe(IMAGE_SAVED, self._on_image_saved)
            bus.unsubscribe(SETTINGS_CHANGED, self._on_settings)
            bus.unsubscribe(APP_CLOSING, self._on_app_closing)

        if self._analyzer is not None:
            try:
                from core.extension_registry import get_extension_registry
                from core.extensions.interfaces import FrameAnalyzer
                registry = get_extension_registry()
                registry.unregister(FrameAnalyzer, self._analyzer)
                self._analyzer.cleanup()
                self._analyzer = None
            except Exception as e:
                logger.error(f"Error desregistrando analyzer: {e}", exc_info=True)

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

    # ==================== HANDLERS ====================

    def _on_image_saved(self, path, frame=None, **kwargs):
        """Handler de IMAGE_SAVED: hace OCR y guarda .txt al lado."""
        if frame is None:
            return
        try:
            from core.settings_manager import settings_manager
            scan = settings_manager.get_scan_settings()
            if not scan.get("enabled", False):
                return

            # OCR en un hilo para no bloquear el bus
            import threading
            threading.Thread(
                target=self._do_ocr,
                args=(path, frame, scan),
                daemon=True,
            ).start()
        except Exception as e:
            logger.error(f"Error en _on_image_saved: {e}", exc_info=True)

    def _do_ocr(self, path, frame, scan_settings):
        try:
            from plugins.document_scanner.scan_manager import ScanManager
            scanner = ScanManager(
                tesseract_path=scan_settings.get("tesseract_path") or None
            )
            result = scanner.process_frame(frame, auto_correct=True)
            text = result.get("text", "").strip()
            if not text:
                return

            import os
            txt_path = os.path.splitext(path)[0] + ".txt"
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(text)
            logger.info(f"📝 OCR guardado: {txt_path} ({len(text)} chars)")
        except Exception as e:
            logger.error(f"Error en OCR: {e}", exc_info=True)

    def _on_settings(self, modules=None, **kwargs):
        if not modules:
            return
        if "scan" in modules and self._analyzer is not None:
            try:
                self._analyzer.reload_config()
            except Exception as e:
                logger.error(f"Error recargando analyzer: {e}")

    def _on_app_closing(self, **kwargs):
        if self._analyzer is not None:
            try:
                self._analyzer.cleanup()
            except Exception:
                pass