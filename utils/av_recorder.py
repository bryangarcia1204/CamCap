"""
Grabador de video con modo dual y TIMING REAL.
- Sin audio: OpenCV con ajuste dinámico de duración
- Con audio: PyAV con PTS reales

FIX v5:
- Mapeo de códecs OpenCV → PyAV (avc1 → libx264)
- Validación real del códec con codec_context.open()
- Opciones H.264 (crf/preset) solo aplicadas a códecs compatibles
- time_base con fallback (Fraction(1, declared_fps))
- Transposición del array de audio para PyAV
- Filtro de decoders (h264_cuvid, mjpeg_cuvid, etc.)
- Soporte Unicode (ruta temporal ASCII + mover al final)
- Logs visibles en errores
"""
import os
import time
import shutil
import tempfile
import threading
import numpy as np
from fractions import Fraction
from typing import Optional

from utils.logger import get_logger

logger = get_logger("AVRecorder")


# ============================================================
# MAPEO DE CÓDECS OpenCV → PyAV/FFmpeg
# ============================================================

CODEC_MAP_OPENCV_TO_PYAV = {
    # H.264
    "avc1": "libx264",
    "h264": "libx264",
    "H264": "libx264",
    "x264": "libx264",
    "X264": "libx264",

    # MPEG-4
    "mp4v": "mpeg4",
    "MP4V": "mpeg4",
    "mpeg4": "mpeg4",

    # XVID
    "XVID": "libxvid",
    "xvid": "libxvid",

    # MJPEG
    "MJPG": "mjpeg",
    "mjpg": "mjpeg",
    "MJPEG": "mjpeg",

    # VP8/VP9
    "VP80": "libvpx",
    "VP90": "libvpx-vp9",
}


# ✅ Códecs preferidos (SOLO ENCODERS, ordenados por prioridad)
FALLBACK_CODECS = [
    "libx264",       # H.264 CPU (máxima calidad)
    "h264_nvenc",    # H.264 NVIDIA GPU
    "h264_qsv",      # H.264 Intel QuickSync
    "h264_amf",      # H.264 AMD
    "mpeg4",         # MPEG-4 (compatible)
    "mjpeg",         # MJPEG (último recurso)
]


# ✅ Decoders que NUNCA se deben usar como encoder
DECODER_ONLY_CODECS = {
    "h264_cuvid", "mjpeg_cuvid", "mpeg1_cuvid", "mpeg2_cuvid",
    "mpeg4_cuvid", "vp8_cuvid", "vp9_cuvid",
    "vp8_qsv", "vp9_qsv", "mjpeg_qsv",
    "h264_d3d12va",
}


# ✅ Códecs que aceptan opciones H.264 (crf/preset)
H264_LIKE_CODECS = {
    "libx264", "libx264rgb", "libx265",
    "h264", "hevc",
    "h264_nvenc", "h264_qsv", "h264_amf",
    "hevc_nvenc", "hevc_qsv", "hevc_amf",
}


def _resolve_pyav_codec(codec_name: str) -> str:
    """Convierte un nombre de códec de OpenCV al que entiende PyAV."""
    if codec_name in CODEC_MAP_OPENCV_TO_PYAV:
        mapped = CODEC_MAP_OPENCV_TO_PYAV[codec_name]
        logger.debug(f"🎬 [codec] '{codec_name}' → '{mapped}'")
        return mapped
    logger.debug(f"🎬 [codec] '{codec_name}' no está en mapa, usando tal cual")
    return codec_name


def _is_ascii_path(path: str) -> bool:
    """Verifica si la ruta es ASCII pura."""
    try:
        path.encode('ascii')
        return True
    except UnicodeEncodeError:
        return False


# ============================================================
# CLASE PRINCIPAL
# ============================================================

class AVRecorder:
    """
    Grabador de video con TIMING REAL y soporte Unicode.
    """

    def __init__(self, output_path: str, fps: int = 30,
                 video_size: tuple = (640, 480),
                 video_codec: str = "avc1",
                 audio_enabled: bool = False,
                 audio_sample_rate: int = 44100,
                 audio_channels: int = 1,
                 audio_device: Optional[int] = None):
        self.output_path = output_path
        self.declared_fps = max(1, fps)
        self.video_size = video_size
        self.video_codec = video_codec
        self.audio_enabled = audio_enabled
        self.audio_sample_rate = audio_sample_rate
        self.audio_channels = audio_channels
        self.audio_device = audio_device

        # Estado
        self._is_running = False
        self._frames_written = 0
        self._start_time = 0.0
        self._end_time = 0.0
        self._lock = threading.Lock()

        # Backend
        self._backend = None

        # OpenCV
        self._cv_writer = None

        # PyAV
        self._container = None
        self._video_stream = None
        self._audio_stream = None
        self._audio_stream_handle = None
        self._audio_buffer = []
        self._audio_buffer_lock = threading.Lock()
        self._av = None
        self._chosen_codec = None

        # ✅ Flags internos
        self._pyav_write_warned = False
        self._time_base_warned = False
        self._codec_validated = False

        # ✅ Ruta temporal si la original tiene Unicode
        self._temp_output_path = None
        self._actual_output_path = output_path

        if not _is_ascii_path(output_path):
            ext = os.path.splitext(output_path)[1] or ".mp4"
            temp_dir = tempfile.gettempdir()
            temp_name = f"procamara_rec_{int(time.time() * 1000)}{ext}"
            self._temp_output_path = os.path.join(temp_dir, temp_name)
            self._actual_output_path = self._temp_output_path

            logger.warning(
                f"⚠️ [rec] Ruta contiene caracteres no-ASCII. "
                f"Se usará temporal: {self._temp_output_path}"
            )

        logger.debug(
            f"🔧 [init] AVRecorder: output={output_path}, "
            f"actual={self._actual_output_path}, "
            f"fps={fps}, size={video_size}, codec={video_codec}, "
            f"audio={audio_enabled}, temp={self._temp_output_path is not None}"
        )

    # ==================== START ====================

    def start(self) -> bool:
        try:
            self._start_time = time.time()

            directory = os.path.dirname(self.output_path)
            if directory and not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
                logger.debug(f"🎬 [rec] Directorio creado: {directory}")

            if self.audio_enabled:
                return self._start_pyav()
            else:
                return self._start_opencv()
        except Exception as e:
            logger.error(f"❌ Error iniciando AVRecorder: {e}", exc_info=True)
            return False

    # ==================== OPENCV (SIN AUDIO) ====================

    def _start_opencv(self) -> bool:
        import cv2

        logger.info(
            f"🎬 Grabando con OpenCV (sin audio): "
            f"{os.path.basename(self._actual_output_path)}"
        )

        format_codecs = {
            '.avi': ['XVID', 'MJPG', 'I420'],
            '.mp4': ['avc1', 'H264', 'X264', 'mp4v'],
            '.mkv': ['X264', 'H264', 'XVID', 'MJPG'],
            '.mov': ['avc1', 'H264', 'mp4v', 'MJPG'],
        }

        ext = os.path.splitext(self._actual_output_path)[1].lower()
        codecs_to_try = [self.video_codec] + format_codecs.get(ext, ['mp4v'])
        seen = set()
        codecs_to_try = [x for x in codecs_to_try if not (x in seen or seen.add(x))]

        logger.debug(
            f"🎬 [rec] Extensión: {ext}, códecs a probar: {codecs_to_try}"
        )

        self._cv_writer = None
        for codec_name in codecs_to_try:
            t0 = time.perf_counter()
            try:
                fourcc = cv2.VideoWriter_fourcc(*codec_name)
                writer = cv2.VideoWriter(
                    self._actual_output_path, fourcc,
                    self.declared_fps, self.video_size
                )
                elapsed_ms = (time.perf_counter() - t0) * 1000
                opened = writer.isOpened()

                logger.debug(
                    f"🎬 [rec] Códec '{codec_name}': fourcc={fourcc}, "
                    f"isOpened={opened}, time={elapsed_ms:.0f}ms"
                )

                if opened:
                    self._cv_writer = writer
                    self._chosen_codec = codec_name
                    logger.info(f"✅ Códec OpenCV: {codec_name}")
                    break
                else:
                    writer.release()
            except Exception as e:
                logger.debug(f"❌ [rec] Códec '{codec_name}' excepción: {e}")
                continue

        if self._cv_writer is None:
            logger.error(
                f"❌ [rec] NO se pudo crear writer. "
                f"Ruta: {self._actual_output_path}, "
                f"Códecs probados: {codecs_to_try}, "
                f"Ext: {ext}, Size: {self.video_size}"
            )
            return False

        self._backend = "opencv"
        self._is_running = True
        self._frames_written = 0
        self._start_time = time.time()
        return True

    # ==================== PYAV (CON AUDIO) ====================

    def _start_pyav(self) -> bool:
        try:
            import av
            self._av = av
            logger.info(
                f"🎬 Grabando con PyAV (con audio): "
                f"{os.path.basename(self._actual_output_path)}"
            )
        except ImportError:
            logger.error("❌ PyAV no instalado. pip install av")
            return False

        # ✅ Verificar directorio escribible
        try:
            directory = os.path.dirname(self._actual_output_path)
            if directory and not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
            test_file = self._actual_output_path + ".test"
            with open(test_file, 'wb') as f:
                f.write(b'test')
            os.remove(test_file)
            logger.debug(f"✅ [pyav] Ruta escribible: {directory or '.'}")
        except Exception as e:
            logger.error(f"❌ [pyav] Ruta NO escribible: {e}", exc_info=True)
            return False

        try:
            # ✅ Resolver códec
            pyav_codec = _resolve_pyav_codec(self.video_codec)
            logger.debug(
                f"🎬 [pyav] Códec: '{self.video_codec}' → '{pyav_codec}'"
            )

            # ✅ Abrir container
            try:
                self._container = av.open(
                    self._actual_output_path, mode='w'
                )
                logger.debug(f"✅ [pyav] Container abierto: {self._actual_output_path}")
            except Exception as e:
                logger.error(
                    f"❌ [pyav] No se pudo abrir container: {e}",
                    exc_info=True
                )
                return False

            # ✅ Construir lista de candidatos válidos (sin decoders)
            candidates = [pyav_codec] + FALLBACK_CODECS
            seen = set()
            candidates_filtered = []
            for c in candidates:
                if c in seen:
                    continue
                if c in DECODER_ONLY_CODECS:
                    logger.debug(f"🎬 [pyav] '{c}' es decoder, saltando")
                    continue
                candidates_filtered.append(c)
                seen.add(c)
            candidates = candidates_filtered

            logger.debug(
                f"🎬 [pyav] Candidatos válidos (encoders): {candidates}"
            )

            # ✅ Probar cada códec VALIDÁNDOLO
            self._video_stream = None
            for codec in candidates:
                try:
                    stream = self._container.add_stream(
                        codec, rate=self.declared_fps
                    )
                    stream.width = self.video_size[0]
                    stream.height = self.video_size[1]
                    stream.pix_fmt = "yuv420p"

                    # ✅ Opciones SOLO a códecs H.264/H.265
                    if codec in H264_LIKE_CODECS:
                        try:
                            stream.options = {'crf': '23', 'preset': 'fast'}
                        except Exception as e:
                            logger.debug(
                                f"⚠️ [pyav] No se pudieron aplicar opciones "
                                f"a '{codec}': {e}"
                            )

                    # ✅ VALIDAR: forzar apertura del códec
                    try:
                        stream.codec_context.open()
                        self._video_stream = stream
                        self._chosen_codec = codec
                        logger.info(
                            f"✅ [pyav] Códec validado y aceptado: '{codec}'"
                        )
                        break
                    except Exception as e:
                        logger.debug(
                            f"🎬 [pyav] Códec '{codec}' no se pudo abrir: "
                            f"{type(e).__name__}: {e}"
                        )
                        try:
                            stream.close()
                        except Exception:
                            pass
                        continue

                except Exception as e:
                    logger.debug(
                        f"🎬 [pyav] Códec '{codec}' rechazado al añadir: "
                        f"{type(e).__name__}: {e}"
                    )
                    continue

            if self._video_stream is None:
                logger.error(
                    f"❌ [pyav] Ningún códec válido. Probados: {candidates}"
                )
                self._cleanup_pyav()
                return False

            # ✅ Audio stream
            try:
                self._audio_stream = self._container.add_stream(
                    'aac', rate=self.audio_sample_rate
                )
                self._audio_stream.layout = (
                    'mono' if self.audio_channels == 1 else 'stereo'
                )
                logger.debug(
                    f"🎬 [rec] Audio: aac, rate={self.audio_sample_rate}, "
                    f"layout={self._audio_stream.layout}"
                )
            except Exception as e:
                logger.warning(
                    f"⚠️ [pyav] No se pudo crear audio stream: {e}"
                )
                self.audio_enabled = False

            # ✅ Iniciar captura de audio
            if self.audio_enabled:
                if not self._start_audio_capture():
                    logger.warning("⚠️ No se pudo iniciar audio, continuando sin él")
                    self.audio_enabled = False

            self._backend = "pyav"
            self._is_running = True
            self._frames_written = 0
            self._start_time = time.time()
            self._codec_validated = True
            logger.info(
                f"✅ AVRecorder (PyAV) iniciado con códec '{self._chosen_codec}'"
            )
            return True

        except Exception as e:
            logger.error(f"❌ Error iniciando PyAV: {e}", exc_info=True)
            self._cleanup_pyav()
            return False

    def _start_audio_capture(self) -> bool:
        try:
            import sounddevice as sd

            try:
                default_input = sd.default.device[0]
                logger.debug(
                    f"🎤 [rec-audio] Dispositivo por defecto: {default_input}"
                )
            except Exception:
                pass

            def audio_callback(indata, frames, time_info, status):
                if status:
                    logger.debug(f"⚠️ [rec-audio] Status: {status}")
                if self._is_running:
                    with self._audio_buffer_lock:
                        self._audio_buffer.append(indata.copy())
                        max_buffer = int(self.audio_sample_rate * 2 / 1024)
                        if len(self._audio_buffer) > max_buffer:
                            self._audio_buffer = self._audio_buffer[-max_buffer:]

            self._audio_stream_handle = sd.InputStream(
                device=self.audio_device,
                channels=self.audio_channels,
                samplerate=self.audio_sample_rate,
                callback=audio_callback,
                blocksize=1024,
                dtype='int16'
            )
            self._audio_stream_handle.start()
            logger.info(f"🎤 Audio capturado: {self.audio_sample_rate}Hz")
            return True

        except ImportError:
            logger.error("sounddevice no instalado. pip install sounddevice")
            return False
        except Exception as e:
            logger.error(f"Error iniciando audio: {e}")
            try:
                import sounddevice as sd
                logger.debug(
                    f"🎤 [rec-audio] Dispositivos: "
                    f"{[d['name'] for d in sd.query_devices()]}"
                )
            except Exception:
                pass
            return False

    # ==================== WRITE FRAME ====================

    def write_frame(self, frame) -> bool:
        """Escribe TODOS los frames sin descartar."""
        if not self._is_running:
            return False

        if frame is None:
            logger.debug("⚠️ [rec] write_frame recibió frame=None")
            return False
        if not hasattr(frame, 'shape') or len(frame.shape) < 2:
            logger.debug(
                f"⚠️ [rec] frame con shape inválido: "
                f"{frame.shape if hasattr(frame, 'shape') else type(frame)}"
            )
            return False

        try:
            if self._backend == "opencv":
                return self._write_frame_opencv(frame)
            elif self._backend == "pyav":
                return self._write_frame_pyav(frame)
        except Exception as e:
            logger.warning(
                f"❌ [rec] Error escribiendo frame: "
                f"{type(e).__name__}: {e}",
                exc_info=True,
            )

        return False

    def _write_frame_opencv(self, frame) -> bool:
        import cv2

        if self._cv_writer is None:
            return False

        h, w = frame.shape[:2]
        if w != self.video_size[0] or h != self.video_size[1]:
            if self._frames_written == 0:
                logger.debug(
                    f"🖼️ [rec] Resize: {w}x{h} → {self.video_size}"
                )
            frame = cv2.resize(
                frame, self.video_size, interpolation=cv2.INTER_LINEAR
            )

        self._cv_writer.write(frame)
        with self._lock:
            self._frames_written += 1
        return True

    def _write_frame_pyav(self, frame) -> bool:
        if self._video_stream is None or self._av is None:
            if not self._pyav_write_warned:
                logger.error(
                    f"❌ [rec] _write_frame_pyav: "
                    f"video_stream={self._video_stream is not None}, "
                    f"av={self._av is not None}"
                )
                self._pyav_write_warned = True
            return False

        try:
            import cv2
            import numpy as np

            h, w = frame.shape[:2]
            if w != self.video_size[0] or h != self.video_size[1]:
                frame = cv2.resize(
                    frame, self.video_size, interpolation=cv2.INTER_LINEAR
                )

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb = np.ascontiguousarray(rgb)

            video_frame = self._av.VideoFrame.from_ndarray(
                rgb, format='rgb24'
            )

            # ✅ PTS con fallback si time_base es None
            time_base = self._video_stream.time_base
            if time_base is None:
                time_base = Fraction(1, self.declared_fps)
                if not self._time_base_warned:
                    logger.debug(
                        f"⚠️ [rec] time_base es None, usando fallback "
                        f"1/{self.declared_fps}"
                    )
                    self._time_base_warned = True

            elapsed = time.time() - self._start_time
            video_frame.pts = int(elapsed * time_base.denominator)
            video_frame.time_base = time_base

            packets_written = 0
            for packet in self._video_stream.encode(video_frame):
                self._container.mux(packet)
                packets_written += 1

            with self._lock:
                self._frames_written += 1

            if self._frames_written % 30 == 0:
                logger.debug(
                    f"📼 [rec] {self._frames_written} frames escritos "
                    f"({packets_written} packets)"
                )

            self._flush_audio_buffer()
            return True

        except Exception as e:
            logger.warning(
                f"❌ [rec] Error escribiendo frame PyAV "
                f"(frame #{self._frames_written}): "
                f"{type(e).__name__}: {e}",
                exc_info=True,
            )
            return False

    def _flush_audio_buffer(self):
        if self._audio_stream is None or self._av is None:
            return

        with self._audio_buffer_lock:
            if not self._audio_buffer:
                return
            buffer_copy = self._audio_buffer
            self._audio_buffer = []

        try:
            import numpy as np

            for audio_chunk in buffer_copy:
                # ✅ Asegurar shape correcto: (channels, samples)
                if audio_chunk.ndim == 2:
                    # sounddevice: (samples, channels) → (channels, samples)
                    audio_chunk = audio_chunk.T
                elif audio_chunk.ndim == 1:
                    # (samples,) → (1, samples)
                    audio_chunk = audio_chunk.reshape(1, -1)

                # ✅ Asegurar contiguo
                audio_chunk = np.ascontiguousarray(audio_chunk)

                # ✅ Crear el frame
                audio_frame = self._av.AudioFrame.from_ndarray(
                    audio_chunk,
                    format='s16',
                    layout='mono' if self.audio_channels == 1 else 'stereo'
                )
                audio_frame.sample_rate = self.audio_sample_rate

                elapsed = time.time() - self._start_time
                audio_frame.pts = int(elapsed * self.audio_sample_rate)

                for packet in self._audio_stream.encode(audio_frame):
                    self._container.mux(packet)

        except Exception as e:
            logger.warning(
                f"❌ [rec] Error escribiendo audio: {type(e).__name__}: {e}"
            )

    # ==================== STOP ====================

    def stop(self) -> Optional[str]:
        if not self._is_running:
            logger.debug("⚠️ [rec] stop() llamado sin estar grabando")
            return None

        self._end_time = time.time()
        self._is_running = False

        try:
            if self._backend == "opencv":
                return self._stop_opencv()
            elif self._backend == "pyav":
                return self._stop_pyav()
        except Exception as e:
            logger.error(f"Error deteniendo AVRecorder: {e}", exc_info=True)

        return self.output_path

    def _stop_opencv(self) -> Optional[str]:
        duration = self._end_time - self._start_time
        frames = self._frames_written

        logger.debug(
            f"⏹ [rec] Cerrando writer OpenCV: "
            f"frames={frames}, duration={duration:.2f}s"
        )

        if self._cv_writer is not None:
            try:
                self._cv_writer.release()
            except Exception:
                pass
            self._cv_writer = None

        if frames > 0 and duration > 0:
            real_fps = frames / duration
            logger.info(
                f"⏹ Grabación OpenCV detenida: "
                f"{frames} frames en {duration:.2f}s "
                f"(FPS real: {real_fps:.1f}, declarado: {self.declared_fps})"
            )
        else:
            logger.info(f"⏹ Grabación OpenCV detenida: {frames} frames")

        return self._finalize_file()

    def _stop_pyav(self) -> Optional[str]:
        logger.debug("⏹ [rec] Cerrando PyAV container...")

        if self._audio_stream_handle is not None:
            try:
                self._audio_stream_handle.stop()
                self._audio_stream_handle.close()
            except Exception as e:
                logger.debug(f"Error deteniendo audio: {e}")
            self._audio_stream_handle = None

        self._flush_audio_buffer()

        # ✅ Flush de video
        if self._video_stream is not None:
            try:
                logger.debug("⏹ [rec] Flush video stream...")
                for packet in self._video_stream.encode():
                    if self._container is not None:
                        self._container.mux(packet)
                logger.debug("⏹ [rec] Video stream flushed")
            except Exception as e:
                logger.warning(
                    f"❌ [rec] Error flush video: {e}", exc_info=True
                )

        # ✅ Flush de audio
        if self._audio_stream is not None:
            try:
                for packet in self._audio_stream.encode():
                    if self._container is not None:
                        self._container.mux(packet)
            except Exception as e:
                logger.debug(f"Error flush audio: {e}")

        # ✅ Cerrar contenedor
        if self._container is not None:
            try:
                logger.debug("⏹ [rec] Cerrando container (escribiendo archivo)...")
                self._container.close()
                logger.debug("⏹ [rec] Container cerrado")
            except Exception as e:
                logger.warning(
                    f"❌ [rec] Error cerrando container: {e}", exc_info=True
                )
            self._container = None

        self._video_stream = None
        self._audio_stream = None
        self._av = None

        duration = self._end_time - self._start_time
        frames = self._frames_written
        real_fps = frames / duration if duration > 0 else self.declared_fps

        logger.info(
            f"⏹ Grabación PyAV detenida: "
            f"{frames} frames en {duration:.2f}s (FPS real: {real_fps:.1f})"
        )

        return self._finalize_file()

    def _finalize_file(self) -> Optional[str]:
        """Mueve el archivo del temporal al destino final si aplica."""

        # Caso 1: Usamos temp path → mover al destino
        if self._temp_output_path and os.path.exists(self._temp_output_path):
            try:
                directory = os.path.dirname(self.output_path)
                if directory and not os.path.exists(directory):
                    os.makedirs(directory, exist_ok=True)

                if os.path.exists(self.output_path):
                    try:
                        os.remove(self.output_path)
                    except Exception:
                        pass

                shutil.move(self._temp_output_path, self.output_path)
                logger.info(
                    f"✅ [rec] Archivo movido de temporal a destino: "
                    f"{self.output_path}"
                )
            except Exception as e:
                logger.error(
                    f"❌ [rec] Error moviendo archivo: {e}", exc_info=True
                )
                if os.path.exists(self._temp_output_path):
                    logger.warning(
                        f"⚠️ [rec] Archivo quedó en temporal: "
                        f"{self._temp_output_path}"
                    )
                    return self._temp_output_path
                return None

        # Caso 2: Ruta original
        if os.path.exists(self.output_path):
            size = os.path.getsize(self.output_path)
            logger.info(
                f"✅ [rec] Archivo: {self.output_path} "
                f"({size/1024/1024:.2f} MB)"
            )
            return self.output_path
        else:
            logger.error(f"❌ [rec] Archivo NO existe: {self.output_path}")

            directory = os.path.dirname(self.output_path)
            logger.error(
                f"❌ [rec] Diagnóstico: directorio='{directory}' "
                f"(existe={os.path.exists(directory)}, "
                f"escribible={os.access(directory, os.W_OK) if os.path.exists(directory) else False})"
            )
            return None

    def _cleanup_pyav(self):
        try:
            if self._audio_stream_handle is not None:
                self._audio_stream_handle.stop()
                self._audio_stream_handle.close()
        except Exception:
            pass
        try:
            if self._container is not None:
                self._container.close()
        except Exception:
            pass
        self._container = None
        self._video_stream = None
        self._audio_stream = None
        self._audio_stream_handle = None
        self._av = None

    # ==================== UTILIDADES ====================

    def is_recording(self) -> bool:
        return self._is_running

    def get_duration(self) -> float:
        if self._start_time == 0:
            return 0.0
        if self._end_time > 0:
            return self._end_time - self._start_time
        return time.time() - self._start_time

    def get_backend(self) -> str:
        return self._backend or "none"

    def get_frames_written(self) -> int:
        return self._frames_written

    def get_real_fps(self) -> float:
        duration = self.get_duration()
        if duration > 0 and self._frames_written > 0:
            return self._frames_written / duration
        return 0.0

    def get_actual_output_path(self) -> str:
        return self._actual_output_path

    def get_chosen_codec(self) -> str:
        return self._chosen_codec or "none"