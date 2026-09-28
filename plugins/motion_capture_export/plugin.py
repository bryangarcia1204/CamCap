"""
Plugin: Motion Capture Export.

Registra:
  - ConfigTab (para la UI de configuración)
  - Métodos públicos para arrancar/detener procesamiento

Modos:
  - Video File: procesa un fragmento de video y exporta animación.
  - Camera Live: (Fase 3) procesa en tiempo real desde cámaras.

El plugin NO conoce el Core internamente. Se engancha vía extensiones
y eventos genéricos.
"""
import os
from typing import Optional, Callable, Dict, Any

from core.plugin_api import BasePlugin
from utils.logger import get_logger

logger = get_logger("Plugin.MotionCaptureExport")


class MotionCaptureExportPlugin(BasePlugin):
    """Plugin de captura de movimiento desde video."""

    NAME = "motion_capture_export"
    VERSION = "1.0.0"
    DESCRIPTION = "Captura de movimiento desde video (YOLO+MediaPipe) para Blender"
    AUTHOR = "ProCamera"
    DEPENDENCIES = []
    REQUIRES_DEBUG = False

    def __init__(self, context):
        super().__init__(context)
        self._tab_provider = None
        self._tracker = None
        self._processor = None
        self._current_config: Dict[str, Any] = {}

    # ==================== CICLO DE VIDA ====================

    def on_load(self) -> bool:
        """Carga modelos. Si falla, el plugin no se activa pero el Core sigue."""
        try:
            from plugins.motion_capture_export.pose_tracker import HybridPoseTracker
            self._tracker = HybridPoseTracker()
            if not self._tracker.load():
                logger.warning(
                    "⚠️ No se pudieron cargar los modelos. "
                    "Instala: pip install ultralytics mediapipe"
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
            from plugins.motion_capture_export.config_tab import (
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
        """Detiene cualquier procesamiento en curso."""
        self.stop_processing()

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
        """Libera modelos."""
        self.stop_processing()
        if self._tracker is not None:
            try:
                self._tracker.release()
            except Exception:
                pass
            self._tracker = None
        self._tab_provider = None
        logger.info("🔌 MotionCaptureExport descargado")

    # ==================== API PÚBLICA ====================

    def start_processing(
        self,
        config: Dict[str, Any],
        on_progress: Optional[Callable] = None,
        on_done: Optional[Callable] = None,
    ) -> bool:
        """
        Inicia el procesamiento de un video.

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
            from plugins.motion_capture_export.video_processor import VideoProcessor
            from plugins.motion_capture_export.exporters import get_exporter

            video_path = config["video_path"]
            output_path = config["output_path"]
            output_format = config.get("output_format", "json")
            frame_skip = config.get("frame_skip", 1)
            max_frames = config.get("max_frames", 0)

            # Configurar tracker con los parámetros del config
            # (en Fase 1 reutilizamos el tracker ya cargado)
            self._processor = VideoProcessor(
                video_path=video_path,
                tracker=self._tracker,
                frame_skip=frame_skip,
                max_frames=max_frames,
            )

            # Callback de resultados → exportar
            def _on_results(results):
                exporter = get_exporter(output_format)
                # Estimar fps de salida
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
        """Detiene el procesamiento en curso (si hay)."""
        if self._processor is not None:
            try:
                self._processor.stop()
            except Exception:
                pass

    def is_processing(self) -> bool:
        """Retorna True si hay un procesamiento en curso."""
        return self._processor is not None and self._processor.is_running()