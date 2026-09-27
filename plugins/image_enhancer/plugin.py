"""
Plugin: Mejora de Imagen.

Registra ImageEnhancer + su ConfigTab.
"""
from core.plugin_api import BasePlugin
from utils.logger import get_logger

logger = get_logger("Plugin.ImageEnhancer")


class ImageEnhancerPlugin(BasePlugin):
    NAME = "image_enhancer"
    VERSION = "1.0.0"
    DESCRIPTION = "Mejora de imágenes con presets y análisis de calidad"
    AUTHOR = "ProCamera"
    DEPENDENCIES = []
    REQUIRES_DEBUG = False

    def __init__(self, context):
        super().__init__(context)
        self._enhancer_class = None
        self._tab_provider = None

    # ==================== CICLO DE VIDA ====================

    def on_load(self) -> bool:
        try:
            from .image_enhancer import ImageEnhancer
            self._enhancer_class = ImageEnhancer
            logger.info("🔌 ImageEnhancerPlugin: clase cargada")
            return True
        except Exception as e:
            logger.error(f"❌ Error cargando ImageEnhancer: {e}", exc_info=True)
            return False

    def on_enable(self) -> bool:
        try:
            from core.extensions.interfaces import UIExtension
            from .widgets import ImageEnhancerUIExtension

            self.register_extension(
                UIExtension,
                ImageEnhancerUIExtension(),
                priority=100,
            )

            # ConfigTab
            from core.extensions.interfaces import ConfigTab
            from core.extensions.config_tab_provider import PluginConfigTabProvider
            from plugins.image_enhancer.config_tab import ImageEnhancerConfigTab

            self._tab_provider = PluginConfigTabProvider(
                plugin_name=self.NAME,
                plugin_context=self.context,
                tab_class=ImageEnhancerConfigTab,
                tab_id="plugin_image_enhancer",
                title="Image Enhancer",
                icon="🎨",
            )
            self.register_extension(ConfigTab, self._tab_provider, priority=170)

            self.logger.info("✅ ImageEnhancer activado (UIExtension + ConfigTab)")
            return True
        except Exception as e:
            self.logger.error(f"❌ Error activando: {e}", exc_info=True)
            return False

    def on_disable(self):
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

        logger.info("⏸️ ImageEnhancerPlugin desactivado")

    def on_unload(self):
        self._enhancer_class = None
        self._tab_provider = None
        logger.info("🔌 ImageEnhancerPlugin descargado")

    # ==================== API PÚBLICA ====================

    def get_class(self):
        return self._enhancer_class

    def get_dialog_class(self):
        try:
            from .enhance_dialog import ImageEnhanceDialog
            return ImageEnhanceDialog
        except Exception as e:
            logger.error(f"❌ Error obteniendo diálogo: {e}")
            return None