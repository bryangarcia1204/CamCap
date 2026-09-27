"""
Motor de captura de video para cámaras IP - v5 (post-limpieza)

Cambios v5:
- Eliminados métodos legacy (setup_detection, _process_detections_legacy)
- Eliminados flags legacy (motion_detection_enabled, face_detection_enabled)
- Solo FrameAnalyzers del ExtensionRegistry
- Lazy load de analyzers corregido
"""
import cv2
import numpy as np
import time
import os
import requests
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Optional, Dict, List

from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker
from PySide6.QtGui import QImage

from core.engine.screen_camera_engine import ScreenCameraManager
from core.engine.local_camera_engine import LocalCameraManager
from core.models import CameraDevice, CameraStatus
from core.event_bus import get_event_bus
from core.events import RECORDING_STARTED, RECORDING_STOPPED, FRAME_READY
from utils.logger import get_logger
from utils.config_loader import advanced_config
from utils.performance import FrameScheduler
from utils.adaptive_throttle import AdaptiveThrottle

logger = get_logger("CameraEngine")


def _notify_lifecycle(event: str, *args):
    """Notifica a los CameraLifecycleListener registrados."""
    try:
        from core.extension_registry import get_extension_registry
        from core.extensions.interfaces import CameraLifecycleListener
        registry = get_extension_registry()
        if registry is None:
            return
        listeners = registry.get(CameraLifecycleListener)
        for listener in listeners:
            try:
                method = getattr(listener, f"on_camera_{event}", None)
                if method is not None:
                    method(*args)
            except Exception as e:
                logger.debug(f"Error en CameraLifecycleListener: {e}")
    except Exception:
        pass


class CameraThread(QThread):
    frame_ready = Signal(QImage)
    status_changed = Signal(CameraStatus)
    error_occurred = Signal(str)
    motion_detected = Signal(int, list)
    face_detected = Signal(int, list, list)
    document_detected = Signal(int, dict)
    text_recognized = Signal(int, str)

    def __init__(self, camera: CameraDevice):
        super().__init__()
        self.camera = camera
        cfg = advanced_config.get_all()

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

        self._running = False
        self._mutex = QMutex()
        self.cap = None
        self._closing = False

        self.fps = cfg["target_fps"]
        self._buffer_size = cfg["buffer_size"]
        self.max_reconnect_attempts = cfg["reconnect_attempts"]
        self._frame_timeout = cfg["frame_timeout"]
        self._detection_frame_skip = cfg["detection_frame_skip"]
        self._scan_frame_skip = cfg["scan_frame_skip"]
        self._connection_timeout = cfg["connection_timeout"]
        self._read_timeout = cfg["read_timeout"]
        self._reconnect_delay = cfg["reconnect_delay"]
        self._gpu_acceleration = cfg["gpu_acceleration"]

        self._executor = ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix=f"CamReader-{camera.id}"
        )

        self._frame_scheduler = FrameScheduler(target_fps=self.fps)
        self._frames_processed = 0
        self._frames_skipped = 0

        try:
            from core.settings_manager import settings_manager
            cs = settings_manager.get_capture_settings()
        except Exception:
            cs = None

        self.last_frame_time = 0
        self.reconnect_attempts = 0
        self._frame_count = 0
        self._video_url = None
        self._target_width = cs.image_resolution.width if cs else 640
        self._target_height = cs.image_resolution.height if cs else 480
        self._last_frame_received = time.time()

        # Grabación
        self._av_recorder = None
        self._is_recording = False
        self._recording_path = None
        self._record_frames_count = 0
        self._recording_fps = 30
        self._record_width = cs.video_resolution.width if cs else 640
        self._record_height = cs.video_resolution.height if cs else 480

        self._last_timeout_check = 0

        # FASE 3: FrameAnalyzers del registry
        self._frame_analyzers: Optional[List] = None
        self._detection_counter = 0

        if self._gpu_acceleration:
            try:
                cv2.ocl.setUseOpenCL(True)
                if not cv2.ocl.haveOpenCL():
                    self._gpu_acceleration = False
            except Exception:
                self._gpu_acceleration = False

    def reload_config(self):
        cfg = advanced_config.get_all()
        self.fps = cfg["target_fps"]
        self._buffer_size = cfg["buffer_size"]
        self.max_reconnect_attempts = cfg["reconnect_attempts"]
        self._frame_timeout = cfg["frame_timeout"]
        self._detection_frame_skip = cfg["detection_frame_skip"]
        self._scan_frame_skip = cfg["scan_frame_skip"]
        self._connection_timeout = cfg["connection_timeout"]
        self._read_timeout = cfg["read_timeout"]
        self._reconnect_delay = cfg["reconnect_delay"]
        if hasattr(self, '_frame_scheduler'):
            self._frame_scheduler.set_fps(self.fps)

        self._frame_analyzers = None

    def refresh_analyzers(self):
        """Fuerza recarga de FrameAnalyzers en el próximo frame."""
        self._frame_analyzers = None

    def run(self):
        with QMutexLocker(self._mutex):
            self._running = True

        self._set_status(CameraStatus.CONNECTING)
        logger.info(f"📹 Iniciando cámara IP: {self.camera.name}")

        if not self._check_connection():
            self._set_status(CameraStatus.DISCONNECTED)
            self.error_occurred.emit(
                f"La cámara {self.camera.name} se encuentra desconectada"
            )
            return

        self._video_url = self._find_working_url()
        if not self._video_url:
            self._set_status(CameraStatus.ERROR)
            self.error_occurred.emit("No se encontró una URL de stream válida")
            return

        self._connect_and_stream(self._video_url)

    # ==================== FASE 3: ANALYZERS ====================

    def _process_detections(self, frame: np.ndarray):
        """Procesa detecciones vía FrameAnalyzers del registry."""
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
        elif kind == "document":
            self.document_detected.emit(self.camera.id, result)
        elif kind == "text":
            text = result.get("text", "")
            if text:
                self.text_recognized.emit(self.camera.id, text)

    def _check_connection(self) -> bool:
        base_url = f"http://{self.camera.ip}:{self.camera.port}"
        try:
            response = requests.get(
                base_url, timeout=self._connection_timeout, stream=True
            )
            response.close()
            return True
        except requests.exceptions.Timeout:
            logger.warning(f"⏱️ [check] {self.camera.name} TIMEOUT")
            return False
        except requests.exceptions.ConnectionError as e:
            logger.warning(f"🔌 [check] {self.camera.name} CONN_ERROR: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ [check] {self.camera.name}: {type(e).__name__}: {e}")
            return False

    def _find_working_url(self) -> Optional[str]:
        base_url = f"http://{self.camera.ip}:{self.camera.port}"
        urls_to_test = [
            f"{base_url}/video",
            f"{base_url}/videofeed",
            f"{base_url}/mjpg/video.mjpg",
            f"{base_url}/cam.mjpg",
            f"{base_url}/stream.mjpg",
        ]

        for url in urls_to_test:
            try:
                cap = cv2.VideoCapture(url)
                if cap.isOpened():
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, self._buffer_size)
                    ret, frame = self._read_with_timeout(cap)
                    if ret and frame is not None:
                        logger.info(
                            f"✅ [find_url] {self.camera.name} URL: {url}"
                        )
                        cap.release()
                        return url
                    cap.release()
            except Exception as e:
                logger.debug(f"❌ [find_url] {url}: {e}")
                continue

        logger.error(f"❌ [find_url] {self.camera.name} ninguna URL funcionó")
        return None

    def _read_with_timeout(self, cap, timeout: float = None):
        if timeout is None:
            timeout = 0.2 if self._closing else self._read_timeout
        try:
            future = self._executor.submit(cap.read)
            ret, frame = future.result(timeout=timeout)
            return ret, frame
        except FutureTimeoutError:
            return False, None
        except Exception:
            return False, None

    def toggle_flash(self, enable: bool) -> bool:
        try:
            base_url = f"http://{self.camera.ip}:{self.camera.port}"
            url = f"{base_url}/enabletorch" if enable else f"{base_url}/disabletorch"
            response = requests.get(url, timeout=self._connection_timeout)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"❌ Error controlando flash: {e}")
            return False

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
        if not self._running:
            return
        logger.info(f"🔌 Desconectando {self.camera.name}")
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
        self._set_status(CameraStatus.DISCONNECTED)

    def _connect_and_stream(self, video_url: str):
        try:
            self.cap = cv2.VideoCapture(video_url)
            if not self.cap.isOpened():
                self._set_status(CameraStatus.ERROR)
                self.error_occurred.emit("No se pudo abrir el stream")
                return

            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, self._buffer_size)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._target_width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._target_height)

            self._set_status(CameraStatus.CONNECTED)
            logger.info("✅ Stream conectado")
            self._last_frame_received = time.time()

            while True:
                with QMutexLocker(self._mutex):
                    if not self._running or self._closing:
                        break

                if self.cap is not None:
                    ret, frame = self._read_with_timeout(self.cap)
                    if self._closing:
                        break

                    if ret and frame is not None:
                        self._frame_count += 1
                        self._adaptive_throttle.check_and_adjust()

                        if not self._adaptive_throttle.should_process_frame(self._frame_count):
                            self._frames_skipped += 1
                            time.sleep(0.001)
                            continue

                        self._frames_processed += 1
                        self._last_frame_received = time.time()
                        frame_start = time.time()

                        now = time.time()
                        if now - self._last_timeout_check >= 1.0:
                            self._last_timeout_check = now

                        # FASE 3: cargar analyzers lazy ANTES de decidir
                        if self._frame_analyzers is None:
                            self._frame_analyzers = self._load_frame_analyzers()

                        if self._frame_analyzers:
                            self._process_detections(frame)

                        h, w = frame.shape[:2]
                        if w != self._target_width or h != self._target_height:
                            frame = cv2.resize(
                                frame, (self._target_width, self._target_height),
                                interpolation=cv2.INTER_LINEAR
                            )

                        self.camera.current_frame = frame.copy()

                        if self._is_recording and self._av_recorder is not None:
                            self._av_recorder.write_frame(frame)
                            self._record_frames_count = self._av_recorder.get_frames_written()

                        try:
                            h, w, ch = frame.shape
                            qt_image = QImage(
                                frame.data, w, h, ch * w,
                                QImage.Format_BGR888
                            ).copy()
                            self.frame_ready.emit(qt_image)
                            # ✅ Emitir FRAME_READY al event bus (para plugins que quieran el frame)
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
                                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                                h, w, ch = rgb.shape
                                qt_image = QImage(
                                    rgb.data, w, h, ch * w,
                                    QImage.Format_RGB888
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
                        self.last_frame_time = self._frame_scheduler.wait_for_next_frame()
                    else:
                        self.reconnect_attempts += 1
                        now = time.time()
                        if now - self._last_timeout_check >= 1.0:
                            self._last_timeout_check = now
                            elapsed = now - self._last_frame_received
                            if elapsed > self._frame_timeout:
                                logger.warning(
                                    f"⚠️ Timeout: {self.camera.name} ({elapsed:.1f}s)"
                                )

                        if self.reconnect_attempts >= self.max_reconnect_attempts:
                            logger.warning(f"🔄 Reconnect: {self.camera.name}")
                            time.sleep(self._reconnect_delay)
                            self._reconnect(video_url)
                            self.reconnect_attempts = 0
                            self._last_frame_received = time.time()

                        time.sleep(0.2)
                else:
                    time.sleep(0.1)

        except Exception as e:
            logger.error(f"❌ Error en stream: {e}", exc_info=True)
            self.error_occurred.emit(f"Error: {str(e)}")
            self._set_status(CameraStatus.ERROR)
        finally:
            self._cleanup()

    def _reconnect(self, video_url: str):
        with QMutexLocker(self._mutex):
            if not self._running:
                return
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

        time.sleep(self._reconnect_delay)
        try:
            self.cap = cv2.VideoCapture(video_url)
            if self.cap.isOpened():
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, self._buffer_size)
                self._set_status(CameraStatus.CONNECTED)
                self._last_frame_received = time.time()
                logger.info("✅ Reconexión exitosa")
            else:
                self._set_status(CameraStatus.ERROR)
                self.error_occurred.emit("Error en reconexión")
        except Exception as e:
            logger.error(f"❌ Error reconectando: {e}")
            self._set_status(CameraStatus.ERROR)

    def _is_running(self) -> bool:
        with QMutexLocker(self._mutex):
            return self._running

    def stop(self):
        if not self._running and not self.isRunning():
            return
        logger.info(f"🛑 Deteniendo thread: {self.camera.name}")
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

        try:
            self._executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass

        if self.isRunning():
            if not self.wait(2000):
                try:
                    self.terminate()
                    self.wait(500)
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
        logger.info(f"✅ Thread detenido: {self.camera.name}")

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

        try:
            self._executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass

        if hasattr(self, '_adaptive_throttle'):
            self._adaptive_throttle.reset()

        if self._frame_analyzers:
            for analyzer in self._frame_analyzers:
                try:
                    if hasattr(analyzer, 'cleanup'):
                        analyzer.cleanup(camera_id=self.camera.id)
                except Exception as e:
                    logger.debug(f"Error en analyzer.cleanup: {e}")

        self.camera.current_frame = None
        if self.camera.status != CameraStatus.ERROR:
            self._set_status(CameraStatus.DISCONNECTED)

    def _set_status(self, status: CameraStatus):
        old_status = self.camera.status
        self.camera.status = status
        self.status_changed.emit(status)

        if status == CameraStatus.CONNECTED and old_status != CameraStatus.CONNECTED:
            _notify_lifecycle("connected", self.camera)
        elif status == CameraStatus.DISCONNECTED and old_status != CameraStatus.DISCONNECTED:
            _notify_lifecycle("disconnected", self.camera)
        elif status == CameraStatus.ERROR:
            _notify_lifecycle("error", self.camera)

    def capture_frame(self) -> Optional[np.ndarray]:
        if self.camera.current_frame is not None:
            return self.camera.current_frame.copy()
        return None


class CameraManager:
    """Gestiona múltiples cámaras."""

    def __init__(self):
        self.cameras: Dict[int, CameraDevice] = {}
        self.threads: Dict[int, CameraThread] = {}
        self.screen_manager = ScreenCameraManager()
        self.local_manager = LocalCameraManager()
        self.screen_camera_id: Optional[int] = None
        self.local_camera_ids: set = set()
        self._op_mutex = QMutex()
        self._closing_ids = set()

    def add_camera(self, camera: CameraDevice) -> bool:
        if camera.id in self._closing_ids:
            return False
        with QMutexLocker(self._op_mutex):
            if camera.id in self.cameras:
                return False
            if camera.is_screen:
                if self.screen_camera_id is not None:
                    return False
                self.screen_camera_id = camera.id
                self.cameras[camera.id] = camera
            elif camera.is_local:
                self.local_camera_ids.add(camera.id)
                self.cameras[camera.id] = camera
            else:
                if not camera.ip or camera.ip == "SCREEN":
                    return False
                self.cameras[camera.id] = camera

        try:
            if camera.is_screen:
                if not self.screen_manager.add_camera(camera):
                    with QMutexLocker(self._op_mutex):
                        self.cameras.pop(camera.id, None)
                        self.screen_camera_id = None
                    return False
            elif camera.is_local:
                if not self.local_manager.add_camera(camera):
                    with QMutexLocker(self._op_mutex):
                        self.cameras.pop(camera.id, None)
                        self.local_camera_ids.discard(camera.id)
                    return False
            else:
                thread = CameraThread(camera)
                self.threads[camera.id] = thread
                thread.start()

            logger.info(f"✅ Cámara añadida: {camera.name}")
            _notify_lifecycle("added", camera)
            return True
        except Exception as e:
            logger.error(f"❌ Error añadiendo cámara: {e}", exc_info=True)
            with QMutexLocker(self._op_mutex):
                self.cameras.pop(camera.id, None)
                if camera.is_screen:
                    self.screen_camera_id = None
                self.local_camera_ids.discard(camera.id)
            return False

    def request_remove_camera(self, camera_id: int, callback=None):
        if camera_id in self._closing_ids:
            if callback:
                callback(camera_id)
            return
        self._closing_ids.add(camera_id)

        with QMutexLocker(self._op_mutex):
            self.cameras.pop(camera_id, None)
            thread = self.threads.pop(camera_id, None)
            is_screen = (self.screen_camera_id == camera_id)
            is_local = (camera_id in self.local_camera_ids)
            screen_thread = self.screen_manager.thread if is_screen else None
            local_thread = self.local_manager.get_thread(camera_id) if is_local else None

            if is_screen:
                self.screen_camera_id = None
                self.screen_manager.camera = None
                self.screen_manager.thread = None
            if is_local:
                self.local_camera_ids.discard(camera_id)
                self.local_manager.cameras.pop(camera_id, None)
                self.local_manager.threads.pop(camera_id, None)

        def worker():
            try:
                target = thread or screen_thread or local_thread
                if target:
                    try:
                        target.disconnect_camera()
                    except Exception:
                        pass
                    try:
                        target.stop()
                    except Exception:
                        pass
            finally:
                self._closing_ids.discard(camera_id)
                if callback:
                    try:
                        callback(camera_id)
                    except Exception:
                        pass

        threading.Thread(target=worker, daemon=True).start()

    def remove_camera(self, camera_id: int) -> bool:
        if camera_id in self._closing_ids:
            return True
        self._closing_ids.add(camera_id)
        try:
            with QMutexLocker(self._op_mutex):
                camera = self.cameras.get(camera_id)
                self.cameras.pop(camera_id, None)
                thread = self.threads.pop(camera_id, None)
                screen_thread = None
                local_thread = None

                if self.screen_camera_id == camera_id:
                    self.screen_camera_id = None
                    screen_thread = self.screen_manager.thread
                    self.screen_manager.camera = None
                    self.screen_manager.thread = None
                if camera_id in self.local_camera_ids:
                    self.local_camera_ids.discard(camera_id)
                    local_thread = self.local_manager.get_thread(camera_id)
                    self.local_manager.cameras.pop(camera_id, None)
                    self.local_manager.threads.pop(camera_id, None)

            for t in [thread, screen_thread, local_thread]:
                if t is None:
                    continue
                try:
                    t.disconnect_camera()
                except Exception:
                    pass
                try:
                    t.stop()
                except Exception:
                    pass

            if camera is not None:
                _notify_lifecycle("removed", camera_id)
            return True
        except Exception as e:
            logger.error(f"Error eliminando cámara: {e}")
            return False
        finally:
            self._closing_ids.discard(camera_id)

    def is_camera_closing(self, camera_id: int) -> bool:
        return camera_id in self._closing_ids

    def get_camera(self, camera_id: int) -> Optional[CameraDevice]:
        return self.cameras.get(camera_id)

    def get_thread(self, camera_id: int):
        if self.screen_camera_id == camera_id:
            return self.screen_manager.get_thread()
        if camera_id in self.local_camera_ids:
            return self.local_manager.get_thread(camera_id)
        return self.threads.get(camera_id)

    def get_active_cameras(self) -> List[CameraDevice]:
        return [c for c in self.cameras.values() if c.status == CameraStatus.CONNECTED]

    def refresh_all_analyzers(self):
        for camera_id, thread in list(self.threads.items()):
            try:
                if hasattr(thread, 'refresh_analyzers'):
                    thread.refresh_analyzers()
            except Exception as e:
                logger.debug(f"Error refresh analyzers {camera_id}: {e}")
        for camera_id in list(self.local_camera_ids):
            thread = self.local_manager.get_thread(camera_id)
            if thread and hasattr(thread, 'refresh_analyzers'):
                try:
                    thread.refresh_analyzers()
                except Exception:
                    pass
        logger.info("🔄 Analyzers refrescados en todas las cámaras")

    def stop_all(self):
        with QMutexLocker(self._op_mutex):
            threads_copy = list(self.threads.values())
            screen_thread = self.screen_manager.thread
            local_threads = list(self.local_manager.threads.values())
            self.threads.clear()
            self.cameras.clear()
            self.local_camera_ids.clear()
            self.screen_camera_id = None
            self.screen_manager.camera = None
            self.screen_manager.thread = None
            self.local_manager.cameras.clear()
            self.local_manager.threads.clear()

        all_threads = threads_copy + local_threads + ([screen_thread] if screen_thread else [])
        for thread in all_threads:
            try:
                thread.disconnect_camera()
            except Exception:
                pass
            try:
                thread.stop()
            except Exception:
                pass
        logger.info("✅ Todas las cámaras detenidas")

    def stop_all_async(self, callback=None):
        def worker():
            try:
                self.stop_all()
            except Exception as e:
                logger.error(f"Error en stop_all_async: {e}", exc_info=True)
            if callback:
                try:
                    callback()
                except Exception:
                    pass
        threading.Thread(target=worker, daemon=True).start()

    def capture_all(self) -> Dict[int, np.ndarray]:
        results = {}
        with QMutexLocker(self._op_mutex):
            threads_copy = dict(self.threads)
            screen_id = self.screen_camera_id
            local_ids = set(self.local_camera_ids)

        for camera_id, thread in threads_copy.items():
            try:
                frame = thread.capture_frame()
                if frame is not None:
                    results[camera_id] = frame
            except Exception:
                pass

        if screen_id is not None:
            thread = self.screen_manager.get_thread()
            if thread:
                frame = thread.capture_frame()
                if frame is not None:
                    results[screen_id] = frame

        for camera_id in local_ids:
            thread = self.local_manager.get_thread(camera_id)
            if thread:
                frame = thread.capture_frame()
                if frame is not None:
                    results[camera_id] = frame

        return results

    def reload_all_configs(self):
        with QMutexLocker(self._op_mutex):
            threads_copy = list(self.threads.values())
            screen_thread = self.screen_manager.thread
            local_threads = [self.local_manager.get_thread(cid) for cid in self.local_camera_ids]

        for thread in threads_copy + local_threads + [screen_thread]:
            if thread and hasattr(thread, 'reload_config'):
                try:
                    thread.reload_config()
                except Exception:
                    pass
        logger.info("🔄 Config recargada en todos los threads")