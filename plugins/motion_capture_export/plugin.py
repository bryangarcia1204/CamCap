"""
Plugin: Motion Capture Export.

Modos:
  - Video File: procesa un archivo y exporta JSON/CSV/BVH.
  - Live Camera: procesa frames en vivo desde las cámaras de CamCap
    y los envía a Blender por socket TCP en tiempo real.

Registra:
  - ConfigTab (botón para abrir el Studio)
  - Métodos públicos para arrancar/detener procesamiento

El plugin NO conoce el Core internamente. Se engancha vía extensiones
y eventos genéricos.
"""
import os
from typing import Optional, Callable, Dict, Any

from core.plugin_api import BasePlugin
from utils.logger import get_logger

logger = get_logger("Plugin.MotionCaptureExport")


class MotionCaptureExportPlugin(BasePlugin):
    """Plugin de captura de movimiento desde video y cámara en vivo."""

    NAME = "motion_capture_export"
    VERSION = "1.0.0"
    DESCRIPTION = "Captura de movimiento (YOLO+MediaPipe) para Blender"
    AUTHOR = "ProCamera"
    DEPENDENCIES = []
    REQUIRES_DEBUG = False

    def __init__(self, context):
        super().__init__(context)
        self._tab_provider = None
        self._tracker = None
        self._processor = None
        self._socket_server = None
        self._live_capture = None
        self._current_config: Dict[str, Any] = {}

    # ==================== CICLO DE VIDA ====================

    def on_load(self) -> bool:
        """Carga modelos YOLO + MediaPipe."""
        try:
            from .pose_tracker import HybridPoseTracker
            self._tracker = HybridPoseTracker()
            if not self._tracker.load():
                logger.warning(
                    "⚠️ No se pudieron cargar los modelos. "
                    "Instala: pip install ultralytics mediapipe opencv-python"
                )
                self._tracker = None
                return False
            logger.info("✅ MotionCaptureExport: modelos cargados")
            return True
        except Exception as e:
            logger.error(f"❌ Error cargando tracker: {e}", exc_info=True)
            self._tracker = None
            return False

    def on_enable(self) -> bool:
        """Registra el ConfigTab."""
        try:
            from core.extensions.interfaces import ConfigTab
            from core.extensions.config_tab_provider import PluginConfigTabProvider
            from .config_tab import (
                MotionCaptureExportConfigTab,
            )

            self._tab_provider = PluginConfigTabProvider(
                plugin_name=self.NAME,
                plugin_context=self.context,
                tab_class=MotionCaptureExportConfigTab,
                tab_id="plugin_motion_capture_export",
                title="Motion Capture Export",
                icon="🎬",
            )
            self.register_extension(ConfigTab, self._tab_provider, priority=200)

            logger.info("✅ MotionCaptureExport activado (ConfigTab)")
            return True
        except Exception as e:
            logger.error(f"❌ Error activando: {e}", exc_info=True)
            return False

    def on_disable(self):
        """Detiene procesamiento y live capture."""
        self.stop_processing()
        self.stop_live()

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

        logger.info("⏸️ MotionCaptureExport desactivado")

    def on_unload(self):
        """Libera recursos."""
        self.stop_processing()
        self.stop_live()

        if self._tracker is not None:
            try:
                self._tracker.release()
            except Exception:
                pass
            self._tracker = None

        self._tab_provider = None
        logger.info("🔌 MotionCaptureExport descargado")

    # ==================== MODO VIDEO (BATCH) ====================

    def start_processing(
        self,
        config: Dict[str, Any],
        on_progress: Optional[Callable] = None,
        on_done: Optional[Callable] = None,
    ) -> bool:
        """
        Inicia el procesamiento de un video (modo batch).

        Args:
            config: dict con video_path, output_path, output_format, etc.
            on_progress: callback(ProcessingProgress)
            on_done: callback(error: Optional[str])

        Returns:
            True si arrancó correctamente.
        """
        if self._tracker is None:
            logger.error("❌ Tracker no disponible (modelos no cargados)")
            if on_done:
                on_done("Modelos no cargados. Instala las dependencias.")
            return False

        if self._processor is not None and self._processor.is_running():
            logger.warning("⚠️ Ya hay un procesamiento en curso")
            return False

        try:
            from .video_processor import VideoProcessor
            from .exporters import get_exporter

            video_path = config["video_path"]
            output_path = config["output_path"]
            output_format = config.get("output_format", "json")
            frame_skip = config.get("frame_skip", 1)
            max_frames = config.get("max_frames", 0)

            self._processor = VideoProcessor(
                video_path=video_path,
                tracker=self._tracker,
                frame_skip=frame_skip,
                max_frames=max_frames,
            )

            def _on_results(results):
                exporter = get_exporter(output_format)
                fps = 30.0
                if len(results) >= 2:
                    dt = results[-1].timestamp - results[0].timestamp
                    if dt > 0:
                        fps = (len(results) - 1) / dt
                exporter.export(results, output_path, video_path, fps)

            self._processor.set_progress_callback(on_progress)
            self._processor.set_result_callback(_on_results)
            self._processor.set_done_callback(on_done)

            self._processor.start()
            self._current_config = dict(config)
            logger.info(f"▶️ Procesamiento iniciado: {os.path.basename(video_path)}")
            return True

        except Exception as e:
            logger.error(f"❌ Error iniciando procesamiento: {e}", exc_info=True)
            if on_done:
                on_done(str(e))
            return False

    def stop_processing(self):
        """Detiene el procesamiento en curso."""
        if self._processor is not None:
            try:
                self._processor.stop()
            except Exception:
                pass

    def is_processing(self) -> bool:
        """True si hay un procesamiento en curso."""
        return self._processor is not None and self._processor.is_running()

    # ==================== MODO LIVE (STREAMING A BLENDER) ====================

    def start_live(
        self,
        host: str = "127.0.0.1",
        port: int = 9999,
        target_fps: int = 15,
        camera_id: Optional[int] = None,
        on_client_connected: Optional[Callable] = None,
        on_client_disconnected: Optional[Callable] = None,
    ) -> bool:
        """
        Inicia el modo Live: socket server + captura en vivo.

        Args:
            host: host donde escucha el socket.
            port: puerto del socket.
            target_fps: FPS objetivo de procesamiento (10-15 en CPU).
            camera_id: si no es None, solo procesa esa cámara.
            on_client_connected: callback cuando un cliente se conecta.
            on_client_disconnected: callback cuando un cliente se desconecta.

        Returns:
            True si arrancó correctamente.
        """
        if self._tracker is None:
            logger.error("❌ Tracker no disponible (modelos no cargados)")
            return False

        if self._live_capture is not None and self._live_capture._running:
            logger.warning("⚠️ Live capture ya está activo")
            return False

        try:
            from .socket_server import SocketServer
            from .live_capture import LiveCapture

            # 1. Crear y arrancar el socket server
            self._socket_server = SocketServer(
                host=host,
                port=port,
                on_client_connected=on_client_connected,
                on_client_disconnected=on_client_disconnected,
            )
            if not self._socket_server.start():
                logger.error(f"❌ No se pudo arrancar el servidor en {host}:{port}")
                self._socket_server = None
                return False

            # 2. Crear y arrancar el live capture
            self._live_capture = LiveCapture(
                tracker=self._tracker,
                socket_server=self._socket_server,
                target_fps=target_fps,
                camera_filter=camera_id,
            )
            if not self._live_capture.start():
                logger.error("❌ No se pudo iniciar la captura en vivo")
                self._socket_server.stop()
                self._socket_server = None
                self._live_capture = None
                return False

            logger.info(
                f"📡 Live iniciado: {host}:{port}, fps={target_fps}, "
                f"camera_filter={camera_id}"
            )
            return True

        except Exception as e:
            logger.error(f"❌ Error iniciando live: {e}", exc_info=True)
            self.stop_live()
            return False

    def stop_live(self):
        """Detiene el modo Live (socket server + captura)."""
        if self._live_capture is not None:
            try:
                self._live_capture.stop()
            except Exception as e:
                logger.debug(f"Error deteniendo live_capture: {e}")
            self._live_capture = None

        if self._socket_server is not None:
            try:
                self._socket_server.stop()
            except Exception as e:
                logger.debug(f"Error deteniendo socket_server: {e}")
            self._socket_server = None

        logger.info("📡 Live detenido")

    def is_live_active(self) -> bool:
        """True si el modo Live está activo."""
        return (
            self._live_capture is not None
            and self._live_capture._running
        )

    def is_client_connected(self) -> bool:
        """True si hay un cliente conectado al socket."""
        if self._socket_server is None:
            return False
        return self._socket_server.is_client_connected()

    def get_live_stats(self) -> Dict[str, Any]:
        """Retorna stats del modo Live."""
        stats: Dict[str, Any] = {
            "active": self.is_live_active(),
            "client_connected": self.is_client_connected(),
        }

        if self._live_capture is not None:
            stats.update(self._live_capture.get_stats())

        if self._socket_server is not None:
            server_stats = self._socket_server.get_stats()
            stats["frames_sent"] = server_stats.get("frames_sent", 0)
            stats["send_errors"] = server_stats.get("send_errors", 0)
            stats["client_address"] = server_stats.get("client_address")

        return stats

    # ==================== API PÚBLICA COMÚN ====================

    def get_tracker(self):
        """Retorna el tracker (para el diálogo)."""
        return self._tracker