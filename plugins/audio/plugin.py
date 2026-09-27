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
            from core.extensions.interfaces import UIExtension
            from .widgets import AudioUIExtension

            self.register_extension(
                UIExtension,
                AudioUIExtension("camera_widget", "header", priority=110),
            )
            self.register_extension(
                UIExtension,
                AudioUIExtension("camera_widget", "footer", priority=110),
            )
            self.register_extension(
                UIExtension,
                AudioUIExtension("main_toolbar", "left", priority=100),
            )
            self.logger.info("✅ AudioPlugin activado (audio UI + toolbar)")
            return True
        except Exception as e:
            self.logger.error(f"❌ Error activando: {e}", exc_info=True)
            return False

    def on_disable(self):
        try:
            from utils.timer_manager import timer_manager
            for name in list(timer_manager.list_timers()):
                if name.startswith("plugin_audio."):
                    timer_manager.stop(name)
        except Exception:
            pass
        self.logger.info("⏸️ AudioPlugin desactivado")

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