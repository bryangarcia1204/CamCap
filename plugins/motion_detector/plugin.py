"""
Plugin: Detector de Movimiento.

Registra:
- MotionDetectorProvider (clase MotionDetector)
- MotionAnalyzer (FrameAnalyzer para CameraThread)
- ConfigTab (visible en SettingsDialog)
"""
from core.plugin_api import BasePlugin
from utils.logger import get_logger

logger = get_logger("Plugin.MotionDetector")


class MotionDetectorPlugin(BasePlugin):
    """Plugin del detector de movimiento."""

    NAME = "motion_detector"
    VERSION = "1.0.0"
    DESCRIPTION = "Detección de movimiento con MOG2/KNN/frame_diff"
    AUTHOR = "ProCamera"
    DEPENDENCIES = []
    REQUIRES_DEBUG = False

    def __init__(self, context):
        super().__init__(context)
        self._motion_class = None
        self._tab_provider = None
        self._analyzer = None

    # ==================== CICLO DE VIDA ====================

    def on_load(self) -> bool:
        """Carga la clase MotionDetector."""
        try:
            from .motion_detector import MotionDetector
            self._motion_class = MotionDetector
            logger.info("🔌 MotionDetectorPlugin: clase cargada")
            return True
        except Exception as e:
            logger.error(f"❌ Error cargando MotionDetector: {e}", exc_info=True)
            return False

    def on_enable(self) -> bool:
        """Registra provider + analyzer + ConfigTab."""
        try:
            # 1. ✅ NUEVO: FrameAnalyzer
            from .analyzer import MotionAnalyzer
            from core.extensions.interfaces import FrameAnalyzer

            self._analyzer = MotionAnalyzer(self.context)
            self.register_extension(
                FrameAnalyzer,
                self._analyzer,
                priority=100,
                metadata={"feature": "motion"},
            )
            logger.debug("🎯 MotionAnalyzer registrado en ExtensionRegistry")

            # 2. ConfigTab
            from core.extensions.interfaces import ConfigTab
            from core.extensions.config_tab_provider import PluginConfigTabProvider
            from .config_tab import MotionDetectorConfigTab

            self._tab_provider = PluginConfigTabProvider(
                plugin_name=self.NAME,
                plugin_context=self.context,
                tab_class=MotionDetectorConfigTab,
                tab_id="plugin_motion_detector",
                title="Motion Detector",
                icon="🚶",
            )
            self.register_extension(
                ConfigTab,
                self._tab_provider,
                priority=100,
            )

            logger.info("✅ MotionDetectorPlugin activado (provider + analyzer + ConfigTab)")
            return True
        except Exception as e:
            logger.error(f"❌ Error activando: {e}", exc_info=True)
            return False

    def on_disable(self):
        """Desregistra analyzer + ConfigTab."""
        # 1. Cleanup analyzer
        if self._analyzer is not None:
            try:
                from core.extension_registry import get_extension_registry
                from core.extensions.interfaces import FrameAnalyzer
                registry = get_extension_registry()
                registry.unregister(FrameAnalyzer, self._analyzer)
                self._analyzer.cleanup()
                self._analyzer = None
                logger.debug("🗑️ MotionAnalyzer desregistrado y limpiado")
            except Exception as e:
                logger.error(f"Error desregistrando MotionAnalyzer: {e}", exc_info=True)

        # 2. Cleanup ConfigTab
        if self._tab_provider is not None:
            try:
                from core.extension_registry import get_extension_registry
                from core.extensions.interfaces import ConfigTab
                registry = get_extension_registry()
                registry.unregister(ConfigTab, self._tab_provider)
                self._tab_provider.cleanup()
                self._tab_provider = None
                logger.debug("🗑️ ConfigTab de motion_detector desregistrada")
            except Exception as e:
                logger.error(f"Error desregistrando ConfigTab: {e}", exc_info=True)

        logger.info("⏸️ MotionDetectorPlugin desactivado")

    def on_unload(self):
        """Limpia recursos."""
        self._motion_class = None
        self._tab_provider = None
        self._analyzer = None
        logger.info("🔌 MotionDetectorPlugin descargado")

    # ==================== API PÚBLICA ====================

    def create_detector(self, sensitivity=None, min_area=None, cooldown_seconds=None):
        """Crea una nueva instancia del MotionDetector."""
        if self._motion_class is None:
            from .motion_detector import MotionDetector
            self._motion_class = MotionDetector

        return self._motion_class(
            sensitivity=sensitivity,
            min_area=min_area,
            cooldown_seconds=cooldown_seconds,
        )

    def get_class(self):
        """Retorna la clase MotionDetector."""
        return self._motion_class

    def get_analyzer(self):
        """Retorna el FrameAnalyzer registrado (para uso interno)."""
        return self._analyzer

    def on_settings_changed(self, changed_keys: list):
        """Notifica al analyzer para que refresque config."""
        if "motion_enabled" in changed_keys or "motion_method" in changed_keys:
            if self._analyzer is not None and hasattr(self._analyzer, "reload_config"):
                try:
                    self._analyzer.reload_config()
                    logger.debug("🔄 MotionAnalyzer recargado tras cambio de settings")
                except Exception as e:
                    logger.error(f"Error recargando analyzer: {e}")
