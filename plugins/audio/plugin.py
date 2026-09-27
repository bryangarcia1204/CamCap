"""
Plugin: Audio.

Se suscribe a:
  - RECORDING_STARTED  → abre un WavWriter para el audio de esa cámara
  - RECORDING_STOPPED  → cierra el WAV y mezcla con el video
  - SETTINGS_CHANGED   → recarga config
  - APP_CLOSING        → limpia

El Core solo graba video. Este plugin escribe el audio en paralelo y
mezcla al final. En PCs de bajos recursos esto reduce el CPU durante
la grabación (no codifica audio en tiempo real).
"""
import os
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
        self._mixer = None
        # camera_id → WavWriter
        self._wav_writers = {}

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
            # 1. UIExtension (widgets de audio en las cámaras + toolbar)
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
            self.register_extension(ConfigTab, self._tab_provider, priority=160)

            # 3. Mezclador
            from plugins.audio.mixer import AudioMixer
            self._mixer = AudioMixer()

            # 4. Suscribirse a eventos
            if self.context.event_bus is not None:
                from core.events import (
                    RECORDING_STARTED,
                    RECORDING_STOPPED,
                    SETTINGS_CHANGED,
                    APP_CLOSING,
                )
                bus = self.context.event_bus
                bus.subscribe(RECORDING_STARTED, self._on_recording_started, owner=self.NAME)
                bus.subscribe(RECORDING_STOPPED, self._on_recording_stopped, owner=self.NAME)
                bus.subscribe(SETTINGS_CHANGED, self._on_settings, owner=self.NAME)
                bus.subscribe(APP_CLOSING, self._on_app_closing, owner=self.NAME)
                logger.debug("🔗 AudioPlugin suscrito a eventos")

            logger.info("✅ AudioPlugin activado (UIExtension + ConfigTab + eventos)")
            return True
        except Exception as e:
            self.logger.error(f"❌ Error activando: {e}", exc_info=True)
            return False

    def on_disable(self):
        # Desuscribirse
        if self.context.event_bus is not None:
            from core.events import (
                RECORDING_STARTED, RECORDING_STOPPED,
                SETTINGS_CHANGED, APP_CLOSING,
            )
            bus = self.context.event_bus
            bus.unsubscribe(RECORDING_STARTED, self._on_recording_started)
            bus.unsubscribe(RECORDING_STOPPED, self._on_recording_stopped)
            bus.unsubscribe(SETTINGS_CHANGED, self._on_settings)
            bus.unsubscribe(APP_CLOSING, self._on_app_closing)

        # Cerrar WAVs abiertos
        for camera_id, writer in list(self._wav_writers.items()):
            try:
                writer.close()
            except Exception:
                pass
        self._wav_writers.clear()

        # Detener timers del plugin
        try:
            from utils.timer_manager import timer_manager
            for name in list(timer_manager.list_timers()):
                if name.startswith("plugin_audio."):
                    timer_manager.stop(name)
        except Exception:
            pass

        # ConfigTab
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

        logger.info("⏸️ AudioPlugin desactivado")

    def on_unload(self):
        try:
            if self._audio_manager is not None:
                self._audio_manager.stop_all()
        except Exception:
            pass
        self._audio_manager = None
        self._tab_provider = None
        self._mixer = None
        self._wav_writers.clear()
        logger.info("🔌 AudioPlugin descargado")

    # ==================== HANDLERS DE EVENTOS ====================

    def _on_recording_started(self, camera_id, camera_name,
                              path, fps=None, width=None, height=None, **kwargs):
        """
        El Core empezó a grabar video. Abrimos un WavWriter en paralelo
        si el usuario tenía audio activado para esta cámara.
        """
        if self._audio_manager is None:
            return
        if not self._audio_manager.is_camera_audio_active(camera_id):
            logger.debug(
                f"🎙️ [rec] {camera_name}: audio no activo, no escribimos WAV"
            )
            return

        # Ruta del WAV: mismo nombre que el video, extensión .wav
        audio_path = os.path.splitext(path)[0] + ".wav"

        try:
            from plugins.audio.wav_writer import WavWriter
            from utils.config_loader import advanced_config
            sample_rate = advanced_config.get("audio_sample_rate", 44100)
            channels = advanced_config.get("audio_channels", 1)

            writer = WavWriter(
                path=audio_path,
                sample_rate=sample_rate,
                channels=channels,
            )
            if not writer.open():
                return
            self._wav_writers[camera_id] = writer

            # Conectar el callback de nivel del stream de audio al writer
            stream = self._audio_manager.get_stream(camera_id)
            if stream is not None:
                # Monkey-patch: cada vez que el stream decodifica un bloque,
                # lo pasamos también al writer.
                original_update = stream._update_level_from_pcm

                def update_and_write(pcm_bytes, _w=writer, _orig=original_update):
                    _orig(pcm_bytes)
                    _w.write(pcm_bytes)

                stream._update_level_from_pcm = update_and_write

            logger.info(
                f"🎙️ [rec] WAV abierto para {camera_name}: {audio_path}"
            )
        except Exception as e:
            logger.error(f"❌ Error abriendo WavWriter: {e}", exc_info=True)

    def _on_recording_stopped(self, camera_id, camera_name, path, **kwargs):
        """
        El Core terminó de grabar. Cerramos el WAV y mezclamos con el video.
        """
        writer = self._wav_writers.pop(camera_id, None)
        if writer is None:
            return

        # Restaurar el método original del stream
        if self._audio_manager is not None:
            stream = self._audio_manager.get_stream(camera_id)
            if stream is not None and hasattr(stream, "_update_level_from_pcm"):
                # El monkey-patch ya no es necesario
                pass

        audio_path = writer.close()
        if not audio_path:
            logger.debug(f"🎙️ [rec] {camera_name}: sin audio, no se mezcla")
            return

        if self._mixer is None:
            logger.warning("⚠️ Mixer no disponible, dejando WAV huérfano")
            return

        # Mezclar en un hilo para no bloquear el event bus
        import threading
        def _mix():
            try:
                self._mixer.mix(
                    video_path=path,
                    audio_path=audio_path,
                    output_path=path,
                    delete_sources=True,
                )
            except Exception as e:
                logger.error(f"❌ Error mezclando: {e}", exc_info=True)

        threading.Thread(target=_mix, daemon=True).start()
        logger.info(f"🎬 [rec] Mezclando video+audio para {camera_name}…")

    def _on_settings(self, modules=None, **kwargs):
        if not modules:
            return
        if "audio" in modules:
            try:
                from utils.config_loader import advanced_config
                advanced_config.reload()
                if self._audio_manager and hasattr(self._audio_manager, 'reload_config'):
                    self._audio_manager.reload_config()
                logger.debug("🔄 Audio recargado tras SETTINGS_CHANGED")
            except Exception as e:
                logger.error(f"Error recargando audio: {e}", exc_info=True)

    def _on_app_closing(self, **kwargs):
        # Cerrar WAVs abiertos
        for camera_id, writer in list(self._wav_writers.items()):
            try:
                writer.close()
            except Exception:
                pass
        self._wav_writers.clear()

    # ==================== API PÚBLICA ====================

    def get_manager(self):
        return self._audio_manager

    def stop_all(self):
        if self._audio_manager is not None:
            self._audio_manager.stop_all()