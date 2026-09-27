"""
Plugin: Reconocimiento Facial.

Registra provider + analyzer + ConfigTab.
"""
from core.plugin_api import BasePlugin
from utils.logger import get_logger

logger = get_logger("Plugin.FaceRecognizer")


class FaceRecognizerPlugin(BasePlugin):
    NAME = "face_recognizer"
    VERSION = "1.0.0"
    DESCRIPTION = "Reconocimiento facial (SFace, dlib, MediaPipe)"
    AUTHOR = "ProCamera"
    DEPENDENCIES = []
    REQUIRES_DEBUG = False

    def __init__(self, context):
        super().__init__(context)
        self._recognizer_class = None
        self._tab_provider = None
        self._analyzer = None

    def on_load(self) -> bool:
        try:
            from .face_recognizer import FaceRecognizer
            self._recognizer_class = FaceRecognizer
            logger.info("🔌 FaceRecognizerPlugin: clase cargada")
            return True
        except Exception as e:
            logger.error(f"❌ Error cargando FaceRecognizer: {e}", exc_info=True)
            return False

    def on_enable(self) -> bool:
        try:
            from .analyzer import FaceAnalyzer
            from core.extensions.interfaces import FrameAnalyzer
            self._analyzer = FaceAnalyzer(self.context)
            self.register_extension(
                FrameAnalyzer, self._analyzer,
                priority=110, metadata={"feature": "face"},
            )
            logger.debug("🎯 FaceAnalyzer registrado en ExtensionRegistry")

            from core.extensions.interfaces import ConfigTab
            from core.extensions.config_tab_provider import PluginConfigTabProvider
            from .config_tab import FaceRecognizerConfigTab
            self._tab_provider = PluginConfigTabProvider(
                plugin_name=self.NAME,
                plugin_context=self.context,
                tab_class=FaceRecognizerConfigTab,
                tab_id="plugin_face_recognizer",
                title="Face Recognizer",
                icon="👤",
            )
            self.register_extension(ConfigTab, self._tab_provider, priority=110)

            logger.info("✅ FaceRecognizerPlugin activado (provider + analyzer + ConfigTab)")
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
                logger.error(f"Error desregistrando FaceAnalyzer: {e}", exc_info=True)

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

        logger.info("⏸️ FaceRecognizerPlugin desactivado")

    def on_unload(self):
        self._recognizer_class = None
        self._tab_provider = None
        self._analyzer = None
        logger.info("🔌 FaceRecognizerPlugin descargado")

    def create_recognizer(self, known_faces_dir="known_faces",
                          tolerance=None, model=None):
        if self._recognizer_class is None:
            from .face_recognizer import FaceRecognizer
            self._recognizer_class = FaceRecognizer
        return self._recognizer_class(
            known_faces_dir=known_faces_dir,
            tolerance=tolerance, model=model,
        )

    def get_class(self):
        return self._recognizer_class

    def get_analyzer(self):
        return self._analyzer

    def on_settings_changed(self, changed_keys: list):
        if "face_enabled" in changed_keys or "face_detector_model" in changed_keys:
            if self._analyzer is not None and hasattr(self._analyzer, "reload_config"):
                try:
                    self._analyzer.reload_config()
                    logger.debug("🔄 FaceAnalyzer recargado tras cambio de settings")
                except Exception as e:
                    logger.error(f"Error recargando analyzer: {e}")