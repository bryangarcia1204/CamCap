"""
Plugin: Mejora de Imagen.

Registra ImageEnhancer y su ConfigTab.
"""
from core.plugin_api import BasePlugin
from utils.logger import get_logger

logger = get_logger("Plugin.ImageEnhancer")


class ImageEnhancerPlugin(BasePlugin):
    """Plugin del mejorador de imágenes."""

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
            from plugins.image_enhancer.image_enhancer import ImageEnhancer
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
            self.logger.info("✅ ImageEnhancer activado (UIExtension)")
            return True
        except Exception as e:
            self.logger.error(f"❌ Error activando: {e}", exc_info=True)
            return False

    def on_disable(self):
        try:
            from core.extension_registry import get_extension_registry
            from core.extensions.interfaces import DialogExtension
            registry = get_extension_registry()
            registry.unregister(DialogExtension, self)
        except Exception:
            pass
        
        if self._tab_provider is not None:
            try:
                from core.extension_registry import get_extension_registry
                from core.extensions.interfaces import ConfigTab
                registry = get_extension_registry()
                registry.unregister(ConfigTab, self._tab_provider)
                self._tab_provider.cleanup()
                self._tab_provider = None
                logger.debug("🗑️ ConfigTab de image_enhancer desregistrada")
            except Exception as e:
                logger.error(f"Error desregistrando ConfigTab: {e}", exc_info=True)

        logger.info("⏸️ ImageEnhancerPlugin desactivado")

    def on_unload(self):
        self._enhancer_class = None
        self._tab_provider = None
        logger.info("🔌 ImageEnhancerPlugin descargado")

    def get_target_dialog(self) -> str:
        return "image_preview"

    def get_widgets(self, dialog, **kwargs):
        from .widgets import create_enhance_button
        return create_enhance_button(dialog, **kwargs)

    def get_priority(self) -> int:
        return 100

    # ==================== API PÚBLICA ====================

    def get_class(self):
        return self._enhancer_class

    def get_dialog_class(self):
        try:
            from plugins.image_enhancer.enhance_dialog import ImageEnhanceDialog
            return ImageEnhanceDialog
        except Exception as e:
            logger.error(f"❌ Error obteniendo diálogo: {e}")
            return None