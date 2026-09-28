"""
Captura en vivo: se suscribe a FRAME_READY y procesa frames
con el tracker, enviándolos por socket a Blender.

Uso:
    capture = LiveCapture(
        tracker=tracker,
        socket_server=server,
        target_fps=15,
    )
    capture.start()
    # ...
    capture.stop()
"""
import time
import threading
from typing import Optional, Callable

from utils.logger import get_logger

logger = get_logger("Plugin.LiveCapture")


class LiveCapture:
    """
    Procesa frames en vivo desde el EventBus de CamCap.

    Se suscribe a FRAME_READY, aplica el tracker a los frames,
    y los envía por el socket. Aplica throttling para no saturar
    la CPU.
    """

    def __init__(
        self,
        tracker,
        socket_server,
        target_fps: int = 15,
        camera_filter: Optional[int] = None,
    ):
        """
        Args:
            tracker: HybridPoseTracker ya cargado.
            socket_server: SocketServer ya iniciado.
            target_fps: FPS objetivo del procesamiento (10-15 en CPU).
            camera_filter: Si no es None, solo procesa esta cámara.
        """
        self.tracker = tracker
        self.socket_server = socket_server
        self.target_fps = max(1, target_fps)
        self.camera_filter = camera_filter

        self._min_interval = 1.0 / self.target_fps
        self._last_process_time = 0.0
        self._running = False
        self._lock = threading.RLock()

        self._frames_processed = 0
        self._frames_skipped = 0
        self._processing_times = []

        # Callback del event bus
        self._on_frame_callback: Optional[Callable] = None

    # ==================== START/STOP ====================

    def start(self) -> bool:
        """Se suscribe al event bus y empieza a procesar."""
        if self._running:
            return True

        try:
            from core.event_bus import get_event_bus
            from core.events import FRAME_READY

            bus = get_event_bus()
            if bus is None:
                logger.error("❌ EventBus no disponible")
                return False

            self._running = True
            self._on_frame_callback = self._handle_frame
            bus.subscribe(FRAME_READY, self._on_frame_callback, owner="LiveCapture")

            # Asegurar que el socket server está corriendo
            if not self.socket_server._running:
                if not self.socket_server.start():
                    logger.error("❌ No se pudo arrancar SocketServer")
                    self._running = False
                    return False

            logger.info(
                f"🎥 LiveCapture iniciado: "
                f"target_fps={self.target_fps}, "
                f"camera_filter={self.camera_filter}"
            )
            return True

        except Exception as e:
            logger.error(f"❌ Error iniciando LiveCapture: {e}", exc_info=True)
            self._running = False
            return False

    def stop(self):
        """Deja de procesar frames."""
        if not self._running:
            return

        self._running = False

        try:
            from core.event_bus import get_event_bus
            from core.events import FRAME_READY

            bus = get_event_bus()
            if bus is not None and self._on_frame_callback is not None:
                bus.unsubscribe(FRAME_READY, self._on_frame_callback)
        except Exception as e:
            logger.debug(f"Error desuscribiendo: {e}")

        self._on_frame_callback = None

        logger.info(
            f"🎥 LiveCapture detenido: "
            f"{self._frames_processed} procesados, "
            f"{self._frames_skipped} saltados"
        )

    # ==================== HANDLER ====================

    def _handle_frame(self, camera_id: int, frame, timestamp: float = 0.0, **kwargs):
        """
        Procesa un frame del EventBus.

        Aplica throttling y envía el resultado por socket.
        """
        if not self._running:
            return

        # Filtrar por cámara
        if self.camera_filter is not None and camera_id != self.camera_filter:
            return

        # Throttling por FPS objetivo
        now = time.time()
        if now - self._last_process_time < self._min_interval:
            self._frames_skipped += 1
            return

        self._last_process_time = now

        # Verificar que hay cliente conectado
        if not self.socket_server.is_client_connected():
            return

        # Procesar el frame con el tracker
        try:
            t0 = time.time()

            result = self.tracker.process_frame(
                frame_bgr=frame,
                frame_index=self._frames_processed,
                timestamp=timestamp,
            )

            elapsed = time.time() - t0
            self._processing_times.append(elapsed)
            if len(self._processing_times) > 30:
                self._processing_times.pop(0)

            self._frames_processed += 1

            # Enviar al cliente
            self._send_result(result)

        except Exception as e:
            logger.error(f"❌ Error procesando frame: {e}", exc_info=True)

    def _send_result(self, result):
        """Envía el resultado del tracker al socket."""
        if not result.persons:
            # Enviar frame vacío para que Blender sepa que no hay detección
            self.socket_server.send_frame({
                "type": "frame",
                "frame_index": int(result.frame_index),
                "timestamp": float(round(result.timestamp, 4)),
                "fps": float(self.target_fps),
                "person": None,
            })
            return

        # Enviar cada persona detectada
        for person in result.persons:
            if not person.landmarks or len(person.landmarks) != 33:
                continue

            self.socket_server.send_frame({
                "type": "frame",
                "frame_index": int(result.frame_index),
                "timestamp": float(round(result.timestamp, 4)),
                "fps": float(self.target_fps),
                "person": {
                    "track_id": int(person.track_id),
                    "bbox": [int(v) for v in person.bbox],
                    "confidence": float(round(person.confidence, 4)),
                    "landmarks": [
                        [float(v) for v in lm]
                        for lm in person.landmarks
                    ],
                },
            })

    # ==================== STATS ====================

    def get_stats(self) -> dict:
        avg_time = 0.0
        if self._processing_times:
            avg_time = sum(self._processing_times) / len(self._processing_times)

        return {
            "running": self._running,
            "frames_processed": self._frames_processed,
            "frames_skipped": self._frames_skipped,
            "avg_processing_ms": avg_time * 1000,
            "effective_fps": (1.0 / avg_time) if avg_time > 0 else 0.0,
            "target_fps": self.target_fps,
            "camera_filter": self.camera_filter,
        }