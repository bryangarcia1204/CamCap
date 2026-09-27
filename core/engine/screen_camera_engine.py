"""
Motor de captura de pantalla - v3
- QImage.Format_BGR888
- AdaptiveThrottle (target más bajo por ser pantalla)
- AVRecorder dual
- _qimage_to_numpy_safe simplificado
"""
import cv2
import numpy as np
import time
import os
from typing import Optional

from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from core.models import CameraDevice, CameraStatus
from core.event_bus import get_event_bus
from core.events import RECORDING_STARTED, RECORDING_STOPPED, FRAME_READY
from utils.logger import get_logger
from utils.config_loader import advanced_config
from utils.performance import FrameScheduler
from utils.adaptive_throttle import AdaptiveThrottle

logger = get_logger("ScreenCamera")


class ScreenCameraThread(QThread):
    frame_ready = Signal(QImage)
    status_changed = Signal(CameraStatus)
    error_occurred = Signal(str)

    def __init__(self, camera: CameraDevice):
        super().__init__()
        self.camera = camera

        cfg = advanced_config.get_all()

        self._running = False
        self._mutex = QMutex()
        self._closing = False

        self.fps = cfg["target_fps"]
        self._frame_timeout = cfg["frame_timeout"]
        self._reconnect_delay = cfg["reconnect_delay"]
        self._gpu_acceleration = cfg["gpu_acceleration"]

        self._frame_scheduler = FrameScheduler(target_fps=self.fps)

        # === Throttle ===
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
        self._frame_count = 0

        self._display_width = 480
        self._display_height = 360

        self._record_width = 0
        self._record_height = 0
        self._screen_width = 0
        self._screen_height = 0

        self._last_frame_received = time.time()

        # Grabación con AVRecorder
        self._av_recorder = None
        self._is_recording = False
        self._recording_path = None
        self._record_frames_count = 0
        self._recording_fps = 15
        self._screen = None

        self._last_frame_original = None
        self._last_frame_display = None

        self._last_timeout_check = 0

        if self._gpu_acceleration:
            try:
                cv2.ocl.setUseOpenCL(True)
            except Exception:
                self._gpu_acceleration = False

        # 🔍 DEBUG: Estado inicial
        logger.debug(
            f"🔧 [init] ScreenCameraThread: fps={self.fps}, "
            f"timeout={self._frame_timeout}, display={self._display_width}x{self._display_height}, "
            f"gpu={self._gpu_acceleration}"
        )
        logger.info(f"⚙️ Pantalla: FPS={self.fps} (limitado), timeout={self._frame_timeout}s")

    def reload_config(self):
        cfg = advanced_config.get_all()
        old_fps = self.fps
        self.fps = cfg["target_fps"]
        self._frame_timeout = cfg["frame_timeout"]
        self._reconnect_delay = cfg["reconnect_delay"]
        self._frame_scheduler.set_fps(self.fps)

        # 🔍 DEBUG: Cambio de config
        logger.debug(
            f"🔄 [reload] Pantalla: fps={old_fps}→{self.fps}, "
            f"timeout={self._frame_timeout}"
        )
        logger.info("🔄 Config recargada para pantalla")

    def run(self):
        with QMutexLocker(self._mutex):
            self._running = True

        self._set_status(CameraStatus.CONNECTING)

        try:
            app = QApplication.instance()
            if app is None:
                raise Exception("QApplication no inicializada")

            screens = app.screens()
            if not screens:
                raise Exception("No se encontraron pantallas")

            self._screen = screens[0]
            screen_size = self._screen.size()
            self._screen_width = screen_size.width()
            self._screen_height = screen_size.height()

            if self._record_width == 0 or self._record_height == 0:
                self._record_width = self._screen_width
                self._record_height = self._screen_height

            test_frame = self._capture_original_frame()
            if test_frame is None:
                raise Exception("No se pudo capturar la pantalla")

            # 🔍 DEBUG: Test frame
            logger.debug(
                f"✅ [run] Test frame OK: shape={test_frame.shape}, "
                f"dtype={test_frame.dtype}, contiguo={test_frame.flags['C_CONTIGUOUS']}"
            )

            logger.info(f"✅ Pantalla conectada: {self._screen.name()}")
            logger.info(f"   Original: {self._screen_width}x{self._screen_height}")
            logger.info(f"   Visualización: {self._display_width}x{self._display_height}")
            logger.info(f"   Grabación: {self._record_width}x{self._record_height}")

            self._set_status(CameraStatus.CONNECTED)
            self._last_frame_received = time.time()

            self._capture_screen_loop()

        except Exception as e:
            logger.error(f"❌ Error capturando pantalla: {e}", exc_info=True)
            self.error_occurred.emit(f"Error capturando pantalla: {str(e)}")
            self._set_status(CameraStatus.ERROR)

    def _qimage_to_numpy_safe(self, qimage: QImage) -> Optional[np.ndarray]:
        try:
            # 🔍 DEBUG: Antes de la conversión
            logger.debug(
                f"🔄 [q2np] QImage: {qimage.width()}x{qimage.height()}, "
                f"format={qimage.format()}, isNull={qimage.isNull()}"
            )

            qimage_rgb = qimage.convertToFormat(QImage.Format_RGB888)
            width = qimage_rgb.width()
            height = qimage_rgb.height()

            if width <= 0 or height <= 0:
                # 🔍 DEBUG: Dimensiones inválidas
                logger.debug(f"⚠️ [q2np] Dimensiones inválidas: {width}x{height}")
                return None

            stride = qimage_rgb.bytesPerLine()
            ptr = qimage_rgb.constBits()
            data = ptr.tobytes() if hasattr(ptr, 'tobytes') else bytes(ptr)

            if stride != width * 3:
                arr = np.frombuffer(data[:height * stride], dtype=np.uint8)
                arr_reshaped = arr.reshape((height, stride))
                arr_rgb = arr_reshaped[:, :width * 3].reshape((height, width, 3))
                # 🔍 DEBUG: Stride no estándar
                logger.debug(
                    f"🔄 [q2np] Stride no estándar: {stride} != {width*3}, "
                    f"recortando array"
                )
            else:
                arr_rgb = np.frombuffer(
                    data[:height * width * 3], dtype=np.uint8
                ).reshape((height, width, 3))

            result = cv2.cvtColor(arr_rgb, cv2.COLOR_RGB2BGR)

            # 🔍 DEBUG: Resultado
            logger.debug(
                f"✅ [q2np] Convertido: shape={result.shape}, "
                f"dtype={result.dtype}, contiguo={result.flags['C_CONTIGUOUS']}"
            )
            return result
        except Exception as e:
            # 🔍 DEBUG: Excepción
            logger.debug(f"❌ [q2np] Excepción: {type(e).__name__}: {e}")
            logger.error(f"Error convirtiendo QImage: {e}")
            return None

    def _capture_original_frame(self) -> Optional[np.ndarray]:
        try:
            if self._screen is None:
                # 🔍 DEBUG: Sin pantalla
                logger.debug("⚠️ [capture] self._screen es None")
                return None

            pixmap = self._screen.grabWindow(0)

            # 🔍 DEBUG: Pixmap capturado
            logger.debug(
                f"📸 [capture] grabWindow: isNull={pixmap.isNull()}, "
                f"size={pixmap.width()}x{pixmap.height()}"
            )

            if pixmap.isNull():
                logger.debug("⚠️ [capture] Pixmap es null")
                return None

            qimage = pixmap.toImage()
            if qimage.isNull():
                logger.debug("⚠️ [capture] QImage es null")
                return None

            return self._qimage_to_numpy_safe(qimage)
        except Exception as e:
            # 🔍 DEBUG: Excepción
            logger.debug(f"❌ [capture] Excepción: {type(e).__name__}: {e}")
            logger.error(f"Error capturando: {e}")
            return None

    def _capture_screen_loop(self):
        while True:
            with QMutexLocker(self._mutex):
                if not self._running or self._closing:
                    break

            try:
                now = time.time()
                if now - self._last_timeout_check >= 1.0:
                    self._last_timeout_check = now
                    self._check_frame_timeout_internal()

                frame_original = self._capture_original_frame()

                with QMutexLocker(self._mutex):
                    if not self._running or self._closing:
                        break

                if frame_original is not None:
                    self._frame_count += 1

                    self._adaptive_throttle.check_and_adjust()
                    should_process = self._adaptive_throttle.should_process_frame(self._frame_count)

                    if not should_process and not self._is_recording:
                        self._frames_skipped += 1
                        time.sleep(0.01)
                        continue

                    self._frames_processed += 1
                    self._last_frame_received = time.time()
                    self._last_frame_original = frame_original
                    self.camera.current_frame = frame_original.copy()

                    frame_start = time.time()

                    # Grabación (siempre, sin skip)
                    if self._is_recording and self._av_recorder is not None:
                        self._av_recorder.write_frame(frame_original)
                        self._record_frames_count = self._av_recorder.get_frames_written()

                        # 🔍 DEBUG: Grabación cada 100 frames
                        if self._record_frames_count % 100 == 0:
                            logger.debug(
                                f"📼 [rec] Pantalla: {self._record_frames_count} frames grabados"
                            )

                    # Visualización
                    if should_process:
                        try:
                            h, w = frame_original.shape[:2]
                            if w != self._display_width or h != self._display_height:
                                frame_display = cv2.resize(
                                    frame_original,
                                    (self._display_width, self._display_height),
                                    interpolation=cv2.INTER_LINEAR
                                )
                            else:
                                frame_display = frame_original

                            self._last_frame_display = frame_display

                            h_disp, w_disp, ch = frame_display.shape
                            qt_image = QImage(
                                frame_display.data,
                                w_disp, h_disp,
                                ch * w_disp,
                                QImage.Format_BGR888
                            ).copy()
                            self.frame_ready.emit(qt_image)

                            if self._frame_count % 5 == 0:
                                try:
                                    get_event_bus().emit(
                                        FRAME_READY,
                                        camera_id=self.camera.id,
                                        frame=frame_display,
                                        timestamp=time.time(),
                                    )
                                except Exception as e:
                                    logger.debug(f"Error emitiendo FRAME_READY: {e}")
                        except Exception as e:
                            # 🔍 DEBUG: Fallo emitiendo
                            logger.debug(
                                f"❌ [capture] Fallo emitiendo: {type(e).__name__}: {e}"
                            )
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
                                        frame=frame_display,
                                        timestamp=time.time(),
                                    )
                                except Exception as e:
                                    logger.debug(f"Error emitiendo FRAME_READY: {e}")
                            except Exception as e2:
                                logger.debug(
                                    f"❌ [capture] Fallback también falló: {e2}"
                                )

                    self._adaptive_throttle.record_frame_time(time.time() - frame_start)

                    if self._closing:
                        break

                    self._frame_scheduler.wait_for_next_frame()

                else:
                    # 🔍 DEBUG: Sin frame en el loop
                    logger.debug("⚠️ [capture] frame_original es None, esperando 50ms")
                    time.sleep(0.05)

            except Exception as e:
                if self._closing:
                    break
                logger.error(f"Error en bucle: {e}", exc_info=True)
                time.sleep(0.1)

        logger.debug("Bucle de captura de pantalla finalizado")

    def _check_frame_timeout_internal(self):
        if self.camera.status == CameraStatus.CONNECTED:
            elapsed = time.time() - self._last_frame_received
            if elapsed > self._frame_timeout:
                logger.warning(f"⚠️ Timeout pantalla: {elapsed:.1f}s")
                self.error_occurred.emit("Timeout: Pantalla sin respuesta")
                self._set_status(CameraStatus.ERROR)

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
        logger.info(f"🔌 Desconectando {self.camera.name}")
        self._closing = True
        with QMutexLocker(self._mutex):
            self._running = False
        self._last_frame_original = None
        self._last_frame_display = None
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
            logger.debug("Thread pantalla ya detenido")
            return

        logger.info("🛑 Deteniendo thread pantalla")
        self._closing = True
        with QMutexLocker(self._mutex):
            self._running = False

        if self._av_recorder is not None:
            try:
                self._av_recorder.stop()
            except Exception:
                pass
            self._av_recorder = None

        if not self.wait(1500):
            logger.warning("⚠️ Thread pantalla no terminó en 1.5s, forzando terminate()")
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
                f"📊 Pantalla: {self._frames_processed} procesados, "
                f"{self._frames_skipped} saltados ({skip_ratio:.1f}%) | "
                f"CPU final: {metrics['cpu_percent']:.0%}"
            )

        # 🔍 DEBUG: Stats finales
        logger.debug(
            f"📊 [stop] Pantalla stats: procesados={self._frames_processed}, "
            f"saltados={self._frames_skipped}, frame_count={self._frame_count}"
        )
        logger.info("✅ Thread pantalla detenido")

    def _set_status(self, status: CameraStatus):
        # 🔍 DEBUG: Cambio de estado
        logger.debug(f"🔄 [status] Pantalla: {self.camera.status} → {status}")
        self.camera.status = status
        self.status_changed.emit(status)

    def capture_frame(self) -> Optional[np.ndarray]:
        if self.camera.current_frame is not None:
            return self.camera.current_frame.copy()
        logger.debug("⚠️ [capture] Pantalla: current_frame es None")
        return None


class ScreenCameraManager:
    def __init__(self):
        self.camera: Optional[CameraDevice] = None
        self.thread: Optional[ScreenCameraThread] = None

    def add_camera(self, camera: CameraDevice) -> bool:
        try:
            self.camera = camera
            self.thread = ScreenCameraThread(camera)
            self.thread.start()
            logger.info("✅ Cámara pantalla añadida")
            return True
        except Exception as e:
            logger.error(f"❌ Error añadiendo pantalla: {e}")
            return False

    def remove_camera(self) -> bool:
        try:
            thread = self.thread
            self.thread = None
            self.camera = None
            if thread is not None:
                thread.disconnect_camera()
                thread.stop()
            logger.info("✅ Cámara pantalla eliminada")
            return True
        except Exception as e:
            logger.error(f"Error eliminando pantalla: {e}")
            return False

    def get_camera(self) -> Optional[CameraDevice]:
        return self.camera

    def get_thread(self) -> Optional[ScreenCameraThread]:
        return self.thread