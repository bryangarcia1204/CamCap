"""
Motor de captura para cámaras locales - v6 (post-limpieza)

Cambios v6:
- Eliminados métodos legacy (setup_detection, _process_detections_legacy)
- Eliminados flags legacy
- Solo FrameAnalyzers del ExtensionRegistry
"""
import cv2
import numpy as np
import time
import os
from typing import Optional, List

from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker
from PySide6.QtGui import QImage

from core.models import CameraDevice, CameraStatus, LocalCameraInfo
from core.event_bus import get_event_bus
from core.events import RECORDING_STARTED, RECORDING_STOPPED, FRAME_READY
from utils.logger import get_logger
from utils.config_loader import advanced_config
from utils.performance import FrameScheduler
from utils.adaptive_throttle import AdaptiveThrottle

logger = get_logger("LocalCamera")


class LocalCameraDetector:
    """Detector de cámaras locales."""

    @staticmethod
    def detect_available_cameras(max_devices: int = 5) -> List[LocalCameraInfo]:
        import contextlib
        import sys

        available = []
        logger.info(f"🔍 Detectando cámaras locales (0-{max_devices-1})")

        @contextlib.contextmanager
        def silence_stderr():
            with open(os.devnull, 'w') as devnull:
                old_stderr = sys.stderr
                sys.stderr = devnull
                try:
                    yield
                finally:
                    sys.stderr = old_stderr

        with silence_stderr():
            for index in range(max_devices):
                try:
                    cap = None
                    if os.name == 'nt':
                        try:
                            cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
                            if not cap.isOpened():
                                cap.release()
                                cap = None
                        except Exception:
                            if cap is not None:
                                cap.release()
                            cap = None
                    if cap is None:
                        try:
                            cap = cv2.VideoCapture(index)
                        except Exception:
                            cap = None
                    if cap is not None and cap.isOpened():
                        ret, frame = cap.read()
                        if ret and frame is not None:
                            info = LocalCameraInfo(
                                index=index,
                                name=f"Cámara Local {index}",
                                backend="dshow" if os.name == 'nt' else "v4l2",
                                available=True,
                            )
                            available.append(info)
                    if cap is not None:
                        cap.release()
                except Exception:
                    continue

        for info in available:
            logger.info(f"  ✅ Cámara {info.index} disponible")
        logger.info(f"✅ {len(available)} cámara(s) detectada(s)")
        return available


class LocalCameraThread(QThread):
    """Thread de cámara local con FrameAnalyzers."""

    frame_ready = Signal(QImage)
    status_changed = Signal(CameraStatus)
    error_occurred = Signal(str)
    motion_detected = Signal(int, list)
    face_detected = Signal(int, list, list)

    def __init__(self, camera: CameraDevice):
        super().__init__()
        self.camera = camera
        cfg = advanced_config.get_all()

        self._running = False
        self._mutex = QMutex()
        self.cap = None
        self._closing = False

        self.fps = cfg["target_fps"]
        self._buffer_size = cfg["buffer_size"]
        self.max_reconnect_attempts = cfg["reconnect_attempts"]
        self._force_camera_fps = cfg["force_camera_fps"]
        self._frame_timeout = cfg["frame_timeout"]
        self._read_timeout = cfg["read_timeout"]
        self._reconnect_delay = cfg["reconnect_delay"]
        self._gpu_acceleration = cfg["gpu_acceleration"]
        self._detection_frame_skip = cfg["detection_frame_skip"]

        self._frame_scheduler = FrameScheduler(target_fps=self.fps)

        if cfg["throttle_enabled"]:
            self._adaptive_throttle = AdaptiveThrottle(
                target_cpu=cfg["throttle_target_cpu"],
                target_gpu=cfg["throttle_target_gpu"],
                max_skip=cfg["throttle_max_skip"],
                check_interval=cfg["throttle_check_interval"],
            )
        else:
            self._adaptive_throttle = AdaptiveThrottle(
                target_cpu=1.5, target_gpu=0.80,
                max_skip=3, check_interval=1.0
            )

        self._frames_processed = 0
        self._frames_skipped = 0
        self.last_frame_time = 0
        self.reconnect_attempts = 0
        self._frame_count = 0
        self._target_width = 640
        self._target_height = 480
        self._last_frame_received = time.time()

        # Grabación
        self._av_recorder = None
        self._is_recording = False
        self._recording_path = None
        self._record_frames_count = 0
        self._recording_fps = 30
        self._record_width = 640
        self._record_height = 480

        self._last_timeout_check = 0
        self._native_width = 0
        self._native_height = 0
        self._native_fps = 0

        # FASE 3: FrameAnalyzers
        self._frame_analyzers: Optional[List] = None
        self._detection_counter = 0

        if self._gpu_acceleration:
            try:
                cv2.ocl.setUseOpenCL(True)
            except Exception:
                self._gpu_acceleration = False

        logger.info(f"⚙️ Local {camera.name}: FPS={self.fps}, buffer={self._buffer_size}")

    def reload_config(self):
        cfg = advanced_config.get_all()
        self.fps = cfg["target_fps"]
        self._buffer_size = cfg["buffer_size"]
        self.max_reconnect_attempts = cfg["reconnect_attempts"]
        self._frame_timeout = cfg["frame_timeout"]
        self._read_timeout = cfg["read_timeout"]
        self._reconnect_delay = cfg["reconnect_delay"]
        self._detection_frame_skip = cfg["detection_frame_skip"]
        self._frame_scheduler.set_fps(self.fps)
        self._frame_analyzers = None
        logger.info(f"🔄 Config recargada: {self.camera.name}")

    def refresh_analyzers(self):
        self._frame_analyzers = None

    # ==================== FASE 3: ANALYZERS ====================

    def _process_detections(self, frame: np.ndarray):
        """Procesa detecciones vía FrameAnalyzers."""
        self._detection_counter += 1
        if self._detection_counter % self._detection_frame_skip != 0:
            return

        if self._frame_analyzers is None:
            self._frame_analyzers = self._load_frame_analyzers()

        if not self._frame_analyzers:
            return

        for analyzer in self._frame_analyzers:
            try:
                if hasattr(analyzer, 'should_run'):
                    if not analyzer.should_run(self.camera.id):
                        continue
                result = analyzer.analyze(self.camera.id, frame)
                if result is None:
                    continue
                self._dispatch_analyzer_result(analyzer, result)
            except Exception as e:
                logger.error(
                    f"❌ Error en FrameAnalyzer "
                    f"({type(analyzer).__name__}) para {self.camera.name}: {e}",
                    exc_info=True,
                )

    def _load_frame_analyzers(self) -> list:
        try:
            from core.extension_registry import get_extension_registry
            from core.extensions.interfaces import FrameAnalyzer
            registry = get_extension_registry()
            if registry is None:
                return []
            return list(registry.get(FrameAnalyzer))
        except Exception as e:
            logger.debug(f"Error cargando FrameAnalyzers: {e}")
            return []

    def _dispatch_analyzer_result(self, analyzer, result: dict):
        kind = result.get("kind")
        if kind == "motion":
            if result.get("notify", False):
                rects = result.get("rects", [])
                self.motion_detected.emit(self.camera.id, rects)
        elif kind == "face":
            locations = result.get("locations", [])
            names = result.get("names", [])
            if names:
                self.face_detected.emit(self.camera.id, locations, names)

    # ==================== RUN ====================

    def run(self):
        with QMutexLocker(self._mutex):
            self._running = True

        self._set_status(CameraStatus.CONNECTING)
        logger.info(f"📹 Iniciando cámara local: {self.camera.name}")

        if not self._open_camera():
            self._set_status(CameraStatus.ERROR)
            self.error_occurred.emit(f"No se pudo abrir la cámara {self.camera.name}")
            return

        self._capture_loop()

    def _open_camera(self) -> bool:
        try:
            index = self.camera.camera_index

            if os.name == 'nt':
                self.cap = cv2.VideoCapture(index, cv2.CAP_MSMF)
                if not self.cap.isOpened():
                    self.cap.release()
                    self.cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
                    if not self.cap.isOpened():
                        self.cap.release()
                        self.cap = cv2.VideoCapture(index)
            else:
                self.cap = cv2.VideoCapture(index)

            if not self.cap.isOpened():
                logger.error(f"❌ No se pudo abrir cámara {index}")
                return False

            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, self._buffer_size)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._target_width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._target_height)
            if self._force_camera_fps:
                self.cap.set(cv2.CAP_PROP_FPS, self.fps)

            self._native_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self._native_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            native_fps = self.cap.get(cv2.CAP_PROP_FPS)
            self._native_fps = int(native_fps) if 0 < native_fps <= 120 else self.fps

            logger.info(
                f"✅ Cámara abierta: {self._native_width}x{self._native_height} "
                f"@ {self.fps}fps"
            )

            ret, test_frame = self.cap.read()
            if not ret or test_frame is None:
                logger.error("❌ No se puede leer frame")
                self.cap.release()
                self.cap = None
                return False

            self._set_status(CameraStatus.CONNECTED)
            self._last_frame_received = time.time()
            return True
        except Exception as e:
            logger.error(f"❌ Error abriendo cámara: {e}", exc_info=True)
            return False

    def _capture_loop(self):
        while True:
            with QMutexLocker(self._mutex):
                if not self._running or self._closing:
                    break

            try:
                if self.cap is None or not self.cap.isOpened():
                    time.sleep(0.1)
                    continue

                now = time.time()
                if now - self._last_timeout_check >= 1.0:
                    self._last_timeout_check = now
                    self._check_frame_timeout_internal()

                ret, frame = self.cap.read()

                if ret and frame is not None:
                    self._frame_count += 1
                    self._adaptive_throttle.check_and_adjust()

                    if not self._adaptive_throttle.should_process_frame(self._frame_count):
                        self._frames_skipped += 1
                        time.sleep(0.001)
                        continue

                    self._last_frame_received = time.time()
                    self._frames_processed += 1                    
                    self.reconnect_attempts = 0
                    frame_start = time.time()

                    # FASE 3: SIEMPRE cargar analyzers lazy
                    if self._frame_analyzers is None:
                        self._frame_analyzers = self._load_frame_analyzers()

                    if self._frame_analyzers:
                        self._process_detections(frame)

                    h, w = frame.shape[:2]
                    if w != self._target_width or h != self._target_height:
                        frame_display = cv2.resize(
                            frame, (self._target_width, self._target_height),
                            interpolation=cv2.INTER_LINEAR,
                        )
                    else:
                        frame_display = frame

                    self.camera.current_frame = frame.copy()

                    if self._is_recording and self._av_recorder is not None:
                        self._av_recorder.write_frame(frame)
                        self._record_frames_count = self._av_recorder.get_frames_written()

                    try:
                        h_disp, w_disp, ch = frame_display.shape
                        qt_image = QImage(
                            frame_display.data, w_disp, h_disp,
                            ch * w_disp, QImage.Format_BGR888
                        ).copy()
                        self.frame_ready.emit(qt_image)
                        if self._frame_count % 5 == 0:
                            try:
                                get_event_bus().emit(
                                    FRAME_READY,
                                    camera_id=self.camera.id,
                                    frame=frame,
                                    timestamp=time.time(),
                                )
                            except Exception as e:
                                logger.debug(f"Error emitiendo FRAME_READY: {e}")
                    except Exception:
                        try:
                            rgb = cv2.cvtColor(frame_display, cv2.COLOR_BGR2RGB)
                            h_disp, w_disp, ch = rgb.shape
                            qt_image = QImage(
                                rgb.data, w_disp, h_disp,
                                ch * w_disp, QImage.Format_RGB888
                            ).copy()
                            self.frame_ready.emit(qt_image)
                            try:
                                get_event_bus().emit(
                                    FRAME_READY,
                                    camera_id=self.camera.id,
                                    frame=frame,
                                    timestamp=time.time(),
                                )
                            except Exception as e:
                                logger.debug(f"Error emitiendo FRAME_READY: {e}")
                        except Exception:
                            pass

                    self._adaptive_throttle.record_frame_time(time.time() - frame_start)
                    self._frame_scheduler.wait_for_next_frame()

                else:
                    self.reconnect_attempts += 1
                    logger.warning(
                        f"⚠️ Frame perdido {self.reconnect_attempts}/"
                        f"{self.max_reconnect_attempts}"
                    )
                    if self.reconnect_attempts >= self.max_reconnect_attempts:
                        logger.warning("🔄 Reconectando...")
                        time.sleep(self._reconnect_delay)
                        self._reconnect()
                        self.reconnect_attempts = 0
                    time.sleep(0.2)
            except Exception as e:
                if self._closing:
                    break
                logger.error(f"❌ Error en bucle: {e}", exc_info=True)
                time.sleep(0.5)

        self._cleanup()

    def _check_frame_timeout_internal(self):
        if self.camera.status == CameraStatus.CONNECTED:
            elapsed = time.time() - self._last_frame_received
            if elapsed > self._frame_timeout:
                logger.warning(f"⚠️ Timeout: {elapsed:.1f}s")
                self.error_occurred.emit(f"Timeout: {self.camera.name}")

    def _reconnect(self):
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
        time.sleep(self._reconnect_delay)
        if self._open_camera():
            logger.info("✅ Reconexión exitosa")
        else:
            self._set_status(CameraStatus.ERROR)
            self.error_occurred.emit("Error reconectando")

    # ==================== GRABACIÓN ====================

    def start_recording(self, output_path: str = None, codec: str = None,
                    fps: int = None) -> bool:
        try:
            from core.settings_manager import settings_manager
            from utils.av_recorder import AVRecorder

            settings = settings_manager.get_capture_settings()
            if fps is None:
                fps = settings.video_fps
            if codec is None:
                codec = settings.video_codec

            video_resolution = settings.video_resolution
            self._record_width = video_resolution.width
            self._record_height = video_resolution.height
            self._recording_fps = fps

            expected_ext = f".{settings.video_format.value}"
            current_ext = os.path.splitext(output_path)[1].lower()
            if current_ext != expected_ext:
                output_path = os.path.splitext(output_path)[0] + expected_ext

            self._recording_path = output_path
            directory = os.path.dirname(output_path)
            if directory and not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)

            # ✅ El Core solo graba VIDEO. Los plugins de audio se
            # suscriben a RECORDING_STARTED para escribir su propio WAV.
            self._av_recorder = AVRecorder(
                output_path=output_path,
                fps=fps,
                video_size=(self._record_width, self._record_height),
                video_codec=codec,
                audio_enabled=False,
            )

            if not self._av_recorder.start():
                self._av_recorder = None
                return False

            self._is_recording = True
            self._record_frames_count = 0
            self._set_status(CameraStatus.RECORDING)
            logger.info(f"✅ Grabación video iniciada ({self._av_recorder.get_backend()})")

            # ✅ Emitir evento
            try:
                get_event_bus().emit(
                    RECORDING_STARTED,
                    camera_id=self.camera.id,
                    camera_name=self.camera.name,
                    path=output_path,
                    fps=fps,
                    width=self._record_width,
                    height=self._record_height,
                )
            except Exception as e:
                logger.debug(f"Error emitiendo RECORDING_STARTED: {e}")

            return True
        except Exception as e:
            logger.error(f"❌ Error iniciando grabación: {e}", exc_info=True)
            return False

    def stop_recording(self) -> Optional[str]:
        if self._av_recorder is not None:
            try:
                path = self._av_recorder.stop()
                self._av_recorder = None
                self._is_recording = False
                self._set_status(CameraStatus.CONNECTED)

                # ✅ Emitir evento
                try:
                    get_event_bus().emit(
                        RECORDING_STOPPED,
                        camera_id=self.camera.id,
                        camera_name=self.camera.name,
                        path=path,
                    )
                except Exception as e:
                    logger.debug(f"Error emitiendo RECORDING_STOPPED: {e}")

                return path
            except Exception as e:
                logger.error(f"Error deteniendo grabación: {e}")
                self._av_recorder = None
        return None

    def is_recording(self) -> bool:
        return self._is_recording

    def disconnect_camera(self):
        self._closing = True
        with QMutexLocker(self._mutex):
            self._running = False
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
        self.camera.current_frame = None
        try:
            self.status_changed.emit(CameraStatus.DISCONNECTED)
        except Exception:
            pass

    def _is_running(self) -> bool:
        with QMutexLocker(self._mutex):
            return self._running

    def stop(self):
        if not self.isRunning():
            return
        self._closing = True
        with QMutexLocker(self._mutex):
            self._running = False

        if self._av_recorder is not None:
            try:
                self._av_recorder.stop()
            except Exception:
                pass
            self._av_recorder = None

        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

        if not self.wait(3000):
            logger.warning(f"⚠️ Thread {self.camera.name} no terminó en 3s, forzando")
            try:
                self.terminate()
                self.wait(1000)
            except Exception:
                pass

        if self._frames_processed > 0 or self._frames_skipped > 0:
            total = self._frames_processed + self._frames_skipped
            skip_ratio = self._frames_skipped / max(1, total) * 100
            metrics = self._adaptive_throttle.get_metrics()
            logger.info(
                f"📊 {self.camera.name}: {self._frames_processed} procesados, "
                f"{self._frames_skipped} saltados ({skip_ratio:.1f}%) | "
                f"CPU final: {metrics['cpu_percent']:.0%}"
            )

    def _cleanup(self):
        if self._av_recorder is not None:
            try:
                self._av_recorder.stop()
            except Exception:
                pass
            self._av_recorder = None
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
        if hasattr(self, '_adaptive_throttle'):
            self._adaptive_throttle.reset()

        if self._frame_analyzers:
            for analyzer in self._frame_analyzers:
                try:
                    if hasattr(analyzer, 'cleanup'):
                        analyzer.cleanup(camera_id=self.camera.id)
                except Exception:
                    pass

        self.camera.current_frame = None
        if self.camera.status != CameraStatus.ERROR:
            self._set_status(CameraStatus.DISCONNECTED)

    def _set_status(self, status: CameraStatus):
        self.camera.status = status
        self.status_changed.emit(status)

    def capture_frame(self) -> Optional[np.ndarray]:
        if self.camera.current_frame is not None:
            return self.camera.current_frame.copy()
        return None


class LocalCameraManager:
    """Gestiona cámaras locales."""

    def __init__(self):
        self.cameras: dict = {}
        self.threads: dict = {}

    def add_camera(self, camera: CameraDevice) -> bool:
        try:
            if camera.id in self.cameras:
                return False
            self.cameras[camera.id] = camera
            thread = LocalCameraThread(camera)
            self.threads[camera.id] = thread
            thread.start()
            logger.info("✅ Cámara local añadida")
            return True
        except Exception as e:
            logger.error(f"❌ Error: {e}", exc_info=True)
            return False

    def remove_camera(self, camera_id: int) -> bool:
        try:
            if camera_id in self.threads:
                self.threads[camera_id].stop()
                del self.threads[camera_id]
            if camera_id in self.cameras:
                del self.cameras[camera_id]
            return True
        except Exception as e:
            logger.error(f"Error: {e}")
            return False

    def get_thread(self, camera_id: int):
        return self.threads.get(camera_id)

    def get_camera(self, camera_id: int) -> Optional[CameraDevice]:
        return self.cameras.get(camera_id)

    def stop_all(self):
        for thread in list(self.threads.values()):
            try:
                thread.stop()
            except Exception:
                pass
        self.threads.clear()
        self.cameras.clear()