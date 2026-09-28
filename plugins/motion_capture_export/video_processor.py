"""
Procesador de video: lee un fragmento, corre el tracker híbrido,
acumula resultados y los pasa al exportador.

Diseñado para correr en un hilo separado (no bloquear la UI).
"""
import os
import time
import threading
from typing import Optional, Callable, List
from dataclasses import dataclass

from utils.logger import get_logger
from plugins.motion_capture_export.pose_tracker import (
    HybridPoseTracker, FrameResult,
)

logger = get_logger("Plugin.VideoProcessor")


@dataclass
class ProcessingProgress:
    """Estado del procesamiento."""
    current_frame: int
    total_frames: int
    fps_processing: float
    elapsed_seconds: float
    eta_seconds: float
    is_running: bool
    is_done: bool
    error: Optional[str] = None

    @property
    def percent(self) -> float:
        if self.total_frames <= 0:
            return 0.0
        return min(100.0, (self.current_frame / self.total_frames) * 100.0)


class VideoProcessor:
    """
    Procesa un video frame a frame con el tracker híbrido.

    Uso:
        processor = VideoProcessor(
            video_path="pelea.mp4",
            tracker=tracker,
            frame_skip=1,
            max_frames=0,  # 0 = todo
        )
        processor.set_progress_callback(lambda p: print(p.percent))
        processor.set_result_callback(lambda results: exporter.export(results))
        processor.start()  # no bloqueante
        ...
        processor.wait()   # bloquear hasta terminar
    """

    def __init__(
        self,
        video_path: str,
        tracker: HybridPoseTracker,
        frame_skip: int = 1,
        max_frames: int = 0,
        target_fps: float = 0.0,
    ):
        """
        Args:
            video_path: ruta del video
            tracker: HybridPoseTracker ya cargado
            frame_skip: procesar 1 de cada N frames (1 = todos)
            max_frames: límite de frames (0 = sin límite)
            target_fps: 0 = usar FPS del video. >0 = forzar este FPS.
        """
        self.video_path = video_path
        self.tracker = tracker
        self.frame_skip = max(1, frame_skip)
        self.max_frames = max_frames
        self.target_fps = target_fps

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._results: List[FrameResult] = []
        self._progress = ProcessingProgress(
            current_frame=0, total_frames=0,
            fps_processing=0.0, elapsed_seconds=0.0,
            eta_seconds=0.0, is_running=False, is_done=False,
        )

        self._progress_callback: Optional[Callable] = None
        self._result_callback: Optional[Callable] = None
        self._done_callback: Optional[Callable] = None

    # ==================== CALLBACKS ====================

    def set_progress_callback(self, cb: Callable[[ProcessingProgress], None]):
        self._progress_callback = cb

    def set_result_callback(self, cb: Callable[[List[FrameResult]], None]):
        self._result_callback = cb

    def set_done_callback(self, cb: Callable[[Optional[str]], None]):
        self._done_callback = cb

    # ==================== CONTROL ====================

    def start(self):
        """Inicia el procesamiento en un hilo daemon."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("⚠️ Procesamiento ya en curso")
            return

        self._stop_event.clear()
        self._results = []
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="VideoProcessor",
        )
        self._thread.start()

    def stop(self):
        """Solicita detener el procesamiento."""
        self._stop_event.set()

    def wait(self, timeout: float = None):
        """Bloquea hasta que termine el hilo."""
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def get_progress(self) -> ProcessingProgress:
        return self._progress

    def get_results(self) -> List[FrameResult]:
        return list(self._results)

    # ==================== LOOP PRINCIPAL ====================

    def _run(self):
        import cv2

        self._progress.is_running = True
        self._progress.is_done = False
        self._progress.error = None
        self._progress.current_frame = 0

        t_start = time.time()

        try:
            cap = cv2.VideoCapture(self.video_path)
            if not cap.isOpened():
                raise Exception(f"No se pudo abrir el video: {self.video_path}")

            # Obtener metadata
            video_fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

            if self.target_fps > 0:
                output_fps = self.target_fps
                frame_step = max(1, int(round(video_fps / self.target_fps)))
            else:
                output_fps = video_fps
                frame_step = self.frame_skip

            # Calcular frames a procesar
            frames_to_process = total_frames
            if self.max_frames > 0:
                frames_to_process = min(total_frames, self.max_frames)

            self._progress.total_frames = frames_to_process

            logger.info(
                f"🎬 Procesando: {os.path.basename(self.video_path)} "
                f"({width}x{height} @ {video_fps:.1f}fps, "
                f"{total_frames} frames, step={frame_step})"
            )

            frame_idx = 0
            processed = 0
            t_last_log = time.time()

            while not self._stop_event.is_set():
                ret, frame = cap.read()
                if not ret:
                    break

                if self.max_frames > 0 and processed >= self.max_frames:
                    break

                # Saltar frames según step
                if frame_idx % frame_step != 0:
                    frame_idx += 1
                    continue

                # Timestamp real del frame en el video
                timestamp = frame_idx / video_fps if video_fps > 0 else 0.0

                # Procesar
                result = self.tracker.process_frame(
                    frame_bgr=frame,
                    frame_index=processed,
                    timestamp=timestamp,
                )
                self._results.append(result)
                processed += 1
                frame_idx += 1

                # Actualizar progreso
                elapsed = time.time() - t_start
                fps_proc = processed / elapsed if elapsed > 0 else 0.0
                eta = (frames_to_process - processed) / fps_proc if fps_proc > 0 else 0.0

                self._progress.current_frame = processed
                self._progress.fps_processing = fps_proc
                self._progress.elapsed_seconds = elapsed
                self._progress.eta_seconds = eta

                if self._progress_callback is not None:
                    try:
                        self._progress_callback(self._progress)
                    except Exception as e:
                        logger.debug(f"Error en progress_callback: {e}")

                # Log cada 5 segundos
                if time.time() - t_last_log > 5.0:
                    t_last_log = time.time()
                    logger.info(
                        f"  📊 {processed}/{frames_to_process} "
                        f"({self._progress.percent:.1f}%) — "
                        f"{fps_proc:.1f} fps, ETA {eta:.1f}s"
                    )

            cap.release()

            # Resultado final
            if self._stop_event.is_set():
                logger.info(f"⏹️ Procesamiento detenido ({processed} frames)")
            else:
                logger.info(
                    f"✅ Procesamiento completado: {processed} frames en "
                    f"{time.time() - t_start:.1f}s"
                )

            # Callback de resultados
            if self._result_callback is not None:
                try:
                    self._result_callback(self._results)
                except Exception as e:
                    logger.error(f"Error en result_callback: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"❌ Error procesando video: {e}", exc_info=True)
            self._progress.error = str(e)

        finally:
            self._progress.is_running = False
            self._progress.is_done = True

            if self._done_callback is not None:
                try:
                    self._done_callback(self._progress.error)
                except Exception as e:
                    logger.debug(f"Error en done_callback: {e}")