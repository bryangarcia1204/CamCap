"""
Plugin: Audio.

Registra el singleton AudioManager y su ConfigTab.
"""
from core.plugin_api import BasePlugin
from utils.logger import get_logger

logger = get_logger("Plugin.Audio")


class AudioPlugin(BasePlugin):
    """Plugin de audio."""

    NAME = "audio"
    VERSION = "1.0.0"
    DESCRIPTION = "Audio para cámaras IP y micrófono local"
    AUTHOR = "ProCamera"
    DEPENDENCIES = []
    REQUIRES_DEBUG = False

    def __init__(self, context):
        super().__init__(context)
        self._audio_manager = None
        self._tab_provider = None

    # ==================== CICLO DE VIDA ====================

    def on_load(self) -> bool:
        try:
            from plugins.audio.audio_manager import audio_manager
            self._audio_manager = audio_manager
            logger.info("🔌 AudioPlugin: singleton cargado")
            return True
        except Exception as e:
            logger.error(f"❌ Error cargando AudioManager: {e}", exc_info=True)
            return False

    def on_enable(self) -> bool:
        try:
            # 1. Provider
            from core.extensions.interfaces import AudioManagerProvider
            self.register_extension(
                AudioManagerProvider,
                self,
                priority=50,
            )

            # ✅ NUEVO: Registrar CameraWidgetExtension
            from core.extensions.interfaces import CameraWidgetExtension
            self.register_extension(
                CameraWidgetExtension,
                self,
                priority=110,   # orden: flash (100), audio (110), auto_flash (120)
            )

            # ✅ NUEVO: Registrar ToolbarContribution
            from core.extensions.interfaces import ToolbarContribution
            self.register_extension(
                ToolbarContribution,
                self,
                priority=100,
            )

            # 2. ConfigTab
            from core.extensions.interfaces import ConfigTab
            from core.extensions.config_tab_provider import PluginConfigTabProvider
            from plugins.audio.config_tab import AudioConfigTab

            self._tab_provider = PluginConfigTabProvider(
                plugin_name=self.NAME,
                plugin_context=self.context,
                tab_class=AudioConfigTab,
                tab_id="plugin_audio",
                title="Audio",
                icon="🎵",
            )
            self.register_extension(
                ConfigTab,
                self._tab_provider,
                priority=140,
            )

            logger.info("✅ AudioPlugin activado (provider + ConfigTab)")
            return True
        except Exception as e:
            logger.error(f"❌ Error activando: {e}", exc_info=True)
            return False

    def on_disable(self):
        # Desregistrar extensiones
        from core.extension_registry import get_extension_registry
        from core.extensions.interfaces import (
            CameraWidgetExtension, ToolbarContribution, ConfigTab,
        )
        registry = get_extension_registry()

        try:
            registry.unregister(CameraWidgetExtension, self)
        except Exception:
            pass
        try:
            registry.unregister(ToolbarContribution, self)
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
                logger.debug("🗑️ ConfigTab de audio desregistrada")
            except Exception as e:
                logger.error(f"Error desregistrando ConfigTab: {e}", exc_info=True)

        logger.info("⏸️ AudioPlugin desactivado")

        # ✅ NUEVO: limpiar timers de audio de todos los widgets
        try:
            from utils.timer_manager import timer_manager
            for name in list(timer_manager.list_timers()):
                if name.startswith("plugin_audio."):
                    timer_manager.stop(name)
        except Exception:
            pass

        logger.info("⏸️ AudioPlugin desactivado")

    def on_unload(self):
        try:
            if self._audio_manager is not None:
                self._audio_manager.stop_all()
        except Exception as e:
            logger.debug(f"Error en stop_all: {e}")
        self._audio_manager = None
        self._tab_provider = None
        logger.info("🔌 AudioPlugin descargado")

    def get_widgets(self, camera_id: int, camera_widget):
        """CameraWidgetExtension: retorna widgets de audio."""
        from .widgets import create_audio_widgets
        return create_audio_widgets(camera_id, camera_widget)

    def get_priority(self) -> int:
        return 110

    def get_buttons(self, main_window):
        """ToolbarContribution: retorna botones de toolbar."""
        from .widgets import create_local_audio_button
        return [create_local_audio_button(main_window)]

    # ==================== API PÚBLICA ====================

    def get_manager(self):
        return self._audio_manager

    def stop_all(self):
        if self._audio_manager is not None:
            self._audio_manager.stop_all()