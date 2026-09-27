"""
Gestor de audio unificado con soporte para IP Webcam (/audio.wav)
y CamCap Server (/audio.pcm).

FIX v3:
- Migrado de pygame a sounddevice (sample rate correcto)
- Detección automática del sample rate real del stream
- Múltiples audios simultáneos sin conflictos
- Sin time.sleep manual (sincronización nativa)
- ✅ NUEVO: Soporte de MUTE (silencia reproducción sin detener captura)
"""
import struct
import threading
import time
from typing import Optional
from enum import Enum

from utils.logger import get_logger

logger = get_logger("AudioManager")


class AudioSource(Enum):
    CAMERA_IP = "camera_ip"
    LOCAL = "local"


# ============================================================
# UTILIDADES
# ============================================================

def _detect_wav_sample_rate(url: str, timeout: float = 3.0) -> Optional[int]:
    """
    Lee el header WAV del stream y extrae el sample rate real.

    Returns:
        Sample rate en Hz, o None si no se pudo detectar.
    """
    import requests
    try:
        r = requests.get(url, stream=True, timeout=timeout)
        header = r.raw.read(44, decode_content=True)
        r.close()

        if not header or len(header) < 44:
            logger.debug(f"🔊 [wav] Header incompleto: {len(header) if header else 0} bytes")
            return None

        if header[:4] != b'RIFF' or header[8:12] != b'WAVE':
            logger.debug(f"🔊 [wav] No es WAV válido: {header[:12]!r}")
            return None

        sample_rate = struct.unpack('<I', header[24:28])[0]
        channels = struct.unpack('<H', header[22:24])[0]
        bits_per_sample = struct.unpack('<H', header[34:36])[0]

        logger.debug(
            f"🔊 [wav] Header WAV detectado: "
            f"sample_rate={sample_rate}Hz, channels={channels}, "
            f"bits={bits_per_sample}"
        )

        if 4000 <= sample_rate <= 192000:
            return sample_rate

        logger.warning(f"⚠️ [wav] Sample rate fuera de rango: {sample_rate}")
        return None

    except Exception as e:
        logger.debug(f"🔊 [wav] Error leyendo header: {type(e).__name__}: {e}")
        return None


# ============================================================
# CLASE BASE
# ============================================================

class AudioStreamBase:
    def __init__(self, sample_rate: int = 44100, channels: int = 1,
                 volume: float = 0.7):
        self.sample_rate = sample_rate
        self.channels = channels
        self.volume = volume
        self._running = False
        self._thread = None
        self._stop_event = threading.Event()

        self._level = 0.0
        self._level_lock = threading.Lock()

        self.level_callback = None

        # ✅ NUEVO: estado de mute
        self._muted = False
        self._mute_lock = threading.Lock()

    def get_level(self) -> float:
        with self._level_lock:
            return self._level

    def _update_level_from_pcm(self, pcm_bytes: bytes):
        try:
            import numpy as np
            samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
            if len(samples) == 0:
                return
            rms = float(np.sqrt(np.mean(samples ** 2)))
            level = min(1.0, rms / 8000.0)
            with self._level_lock:
                self._level = level
            if self.level_callback:
                try:
                    self.level_callback(level)
                except Exception:
                    pass
        except Exception:
            pass

    # ✅ NUEVO: Mute / Unmute
    def set_muted(self, muted: bool):
        """Mutea/desmutea la reproducción. La captura sigue activa."""
        with self._mute_lock:
            self._muted = muted
        logger.debug(
            f"🔇 [mute] set_muted({muted}) — "
            f"captura sigue activa, salida {'silenciada' if muted else 'activa'}"
        )

    def is_muted(self) -> bool:
        with self._mute_lock:
            return self._muted

    def start(self) -> bool:
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError

    def set_volume(self, volume: float):
        self.volume = max(0.0, min(1.0, volume))

    def is_running(self) -> bool:
        return self._running


# ============================================================
# AUDIO DE CÁMARA IP
# ============================================================

class CameraAudioStream(AudioStreamBase):
    """
    Reproduce audio desde cámara IP.
    """

    AUDIO_ENDPOINTS = [
        ("/audio.wav", "wav"),
        ("/audio.pcm", "pcm"),
        ("/audio", "wav"),
    ]

    def __init__(self, ip: str, port: int = 4747,
                 sample_rate: int = 44100, channels: int = 1,
                 volume: float = 0.7):
        super().__init__(sample_rate, channels, volume)
        self.ip = ip
        self.port = port
        self._stream_sample_rate = sample_rate

        logger.debug(
            f"🔊 [init] CameraAudioStream: {ip}:{port}, "
            f"mixer_rate={sample_rate}Hz, channels={channels}, "
            f"volume={volume}"
        )

    def start(self) -> bool:
        try:
            import sounddevice as sd
            import numpy as np
        except ImportError as e:
            logger.error(
                f"❌ sounddevice/numpy no instalados: {e}\n"
                f"   pip install sounddevice numpy"
            )
            return False

        if self._running:
            logger.debug(f"🔊 [start] {self.ip}: ya estaba corriendo")
            return True

        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name=f"CameraAudio-{self.ip}")
        self._thread.start()
        logger.info(f"🔊 Audio cámara iniciado: {self.ip}:{self.port}")
        return True

    def _detect_endpoint(self) -> Optional[tuple]:
        """Detecta el endpoint de audio correcto."""
        import requests

        base_url = f"http://{self.ip}:{self.port}"
        logger.debug(f"🔊 [detect] Probando endpoints de audio en {base_url}")

        for endpoint, fmt in self.AUDIO_ENDPOINTS:
            url = f"{base_url}{endpoint}"
            try:
                r = requests.head(url, timeout=2, allow_redirects=True)
                logger.debug(
                    f"🔊 [detect] {endpoint} → status={r.status_code}"
                )
                if r.status_code == 200:
                    logger.info(f"🎵 Endpoint audio detectado: {endpoint} ({fmt})")
                    return url, fmt
            except Exception as e:
                logger.debug(
                    f"🔊 [detect] {endpoint} falló: {type(e).__name__}: {e}"
                )
                continue

        url = f"{base_url}/audio.wav"
        logger.warning(f"⚠️ No se detectó endpoint, probando fallback: {url}")
        return url, "wav"

    def _run(self):
        try:
            import sounddevice as sd
            import numpy as np
            import requests

            # 1. Detectar endpoint
            endpoint_info = self._detect_endpoint()
            if endpoint_info is None:
                logger.error("❌ No se encontró endpoint de audio")
                return

            url, fmt = endpoint_info

            # 2. Detectar sample rate real si es WAV
            detected_rate = None
            if fmt == "wav":
                detected_rate = _detect_wav_sample_rate(url)
                if detected_rate:
                    self._stream_sample_rate = detected_rate
                    logger.info(
                        f"🎵 Sample rate real detectado: {detected_rate}Hz "
                        f"(mixer: {self.sample_rate}Hz)"
                    )
                else:
                    logger.warning(
                        f"⚠️ No se pudo detectar sample rate, "
                        f"usando default: {self.sample_rate}Hz"
                    )
                    self._stream_sample_rate = self.sample_rate
            else:
                self._stream_sample_rate = self.sample_rate

            # 3. Abrir stream de output
            out_stream = sd.OutputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype='float32',
                blocksize=0,
                latency='low',
            )
            out_stream.start()
            logger.debug(
                f"🔊 [run] OutputStream abierto: "
                f"samplerate={self.sample_rate}Hz, ch={self.channels}"
            )

            with requests.get(url, stream=True, timeout=(3, 30)) as r:
                if r.status_code != 200:
                    logger.error(f"❌ Error HTTP audio: {r.status_code}")
                    out_stream.stop()
                    out_stream.close()
                    return

                bytes_per_sample = 2 * self.channels
                min_bytes = int(self._stream_sample_rate * bytes_per_sample * 0.05)

                logger.debug(
                    f"🔊 [run] Leyendo stream: "
                    f"bytes_per_sample={bytes_per_sample}, "
                    f"min_bytes={min_bytes} (50ms)"
                )

                if fmt == "wav":
                    header = r.raw.read(44, decode_content=True)
                    if not header or len(header) < 44:
                        logger.warning(
                            f"⚠️ Header WAV incompleto: "
                            f"{len(header) if header else 0} bytes"
                        )
                    else:
                        logger.debug(f"🔊 [run] Header WAV descartado (44 bytes)")

                buffer = bytearray()
                blocks_played = 0

                for chunk in r.iter_content(chunk_size=4096):
                    if self._stop_event.is_set():
                        break
                    if not chunk:
                        continue

                    buffer.extend(chunk)

                    while len(buffer) >= min_bytes:
                        block = bytes(buffer[:min_bytes])
                        del buffer[:min_bytes]

                        # Actualizar nivel (para VU meter)
                        self._update_level_from_pcm(block)

                        # Convertir a float32
                        try:
                            audio_array = np.frombuffer(block, dtype=np.int16)
                            if self.channels > 1:
                                audio_array = audio_array.reshape(-1, self.channels)
                            audio_array = audio_array.astype(np.float32) / 32768.0

                            # ✅ NUEVO: Chequeo de mute
                            with self._mute_lock:
                                is_muted = self._muted

                            if is_muted:
                                audio_array = np.zeros_like(audio_array)
                            else:
                                audio_array *= self.volume
                        except Exception as e:
                            logger.debug(f"🔊 [run] Error convirtiendo bloque: {e}")
                            continue

                        # Escribir al stream
                        try:
                            out_stream.write(audio_array)
                            blocks_played += 1

                            if blocks_played % 100 == 0:
                                logger.debug(
                                    f"🔊 [run] {blocks_played} bloques reproducidos "
                                    f"({len(buffer)} bytes en buffer, "
                                    f"muted={is_muted})"
                                )
                        except Exception as e:
                            logger.debug(f"🔊 [run] Error escribiendo al stream: {e}")
                            break

            out_stream.stop()
            out_stream.close()
            logger.debug(
                f"🔊 [run] Stream cerrado. Total bloques: {blocks_played}"
            )

        except Exception as e:
            logger.error(f"❌ Error en CameraAudioStream: {e}", exc_info=True)
        finally:
            self._running = False
            with self._level_lock:
                self._level = 0.0

    def stop(self):
        if not self._running:
            return
        logger.debug(f"🔊 [stop] Deteniendo audio cámara {self.ip}")
        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("🔇 Audio cámara detenido")


# ============================================================
# AUDIO LOCAL (MICRÓFONO DEL PC)
# ============================================================

class LocalAudioStream(AudioStreamBase):
    """
    Reproduce el micrófono del PC usando sounddevice.
    """

    def __init__(self, sample_rate: int = 44100, channels: int = 1,
                 volume: float = 0.7):
        super().__init__(sample_rate, channels, volume)
        logger.debug(
            f"🔊 [init] LocalAudioStream: "
            f"rate={sample_rate}Hz, ch={channels}, volume={volume}"
        )

    def start(self) -> bool:
        try:
            import sounddevice as sd
            import numpy as np
        except ImportError as e:
            logger.error(
                f"❌ sounddevice/numpy no instalados: {e}\n"
                f"   pip install sounddevice numpy"
            )
            return False

        if self._running:
            logger.debug("🔊 [start] LocalAudio ya estaba corriendo")
            return True

        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="LocalAudio")
        self._thread.start()
        logger.info("🎤 Audio local iniciado")
        return True

    def _run(self):
        try:
            import sounddevice as sd
            import numpy as np

            try:
                default_input = sd.default.device[0]
                logger.debug(
                    f"🔊 [run] Dispositivo de entrada por defecto: "
                    f"{default_input}"
                )
            except Exception as e:
                logger.debug(f"🔊 [run] Error consultando default device: {e}")

            blocksize = 1024

            out_stream = sd.OutputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype='float32',
                blocksize=blocksize,
                latency='low',
            )
            out_stream.start()
            logger.debug(
                f"🔊 [run] OutputStream local abierto: "
                f"{self.sample_rate}Hz, ch={self.channels}"
            )

            def input_callback(indata, frames, time_info, status):
                if status:
                    logger.debug(f"🔊 [mic] Status: {status}")

                if self._stop_event.is_set():
                    return

                # Actualizar nivel (siempre, incluso si está muteado)
                pcm_bytes = indata.tobytes()
                self._update_level_from_pcm(pcm_bytes)

                # Convertir a float32
                try:
                    audio = indata.astype(np.float32) / 32768.0

                    # ✅ NUEVO: Chequeo de mute
                    with self._mute_lock:
                        is_muted = self._muted

                    if is_muted:
                        audio = np.zeros_like(audio)
                    else:
                        audio *= self.volume

                    out_stream.write(audio)
                except Exception as e:
                    logger.debug(f"🔊 [mic] Error escribiendo: {e}")

            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype='int16',
                blocksize=blocksize,
                callback=input_callback
            ):
                logger.info(
                    f"🎤 Capturando micrófono del PC: "
                    f"{self.sample_rate}Hz, ch={self.channels}"
                )

                while not self._stop_event.is_set():
                    sd.sleep(100)

            out_stream.stop()
            out_stream.close()
            logger.debug("🔊 [run] Streams locales cerrados")

        except Exception as e:
            logger.error(f"❌ Error en LocalAudioStream: {e}", exc_info=True)
        finally:
            self._running = False
            with self._level_lock:
                self._level = 0.0

    def stop(self):
        if not self._running:
            return
        logger.debug("🔊 [stop] Deteniendo audio local")
        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("🔇 Audio local detenido")


# ============================================================
# GESTOR PRINCIPAL
# ============================================================

class AudioManager:
    """
    Gestor centralizado de audio.

    FIX v3: mute sin detener la captura.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        self.streams: dict = {}
        logger.info("🎵 AudioManager inicializado")
        logger.debug(
            "🎵 [init] FIX v3 activo: sounddevice + mute + sample rate"
        )

    def get_stream(self, camera_id: int) -> Optional[AudioStreamBase]:
        return self.streams.get(camera_id)

    def get_level(self, camera_id: int) -> float:
        stream = self.streams.get(camera_id)
        if stream:
            return stream.get_level()
        return 0.0

    def set_level_callback(self, camera_id: int, callback):
        stream = self.streams.get(camera_id)
        if stream:
            stream.level_callback = callback

    def start_camera_audio(self, camera_id: int, ip: str, port: int,
                           volume: float = 0.7) -> bool:
        logger.debug(
            f"🔊 [manager] start_camera_audio: id={camera_id}, "
            f"ip={ip}:{port}, volume={volume}"
        )

        if camera_id in self.streams:
            logger.debug(
                f"🔊 [manager] Cámara {camera_id} ya tiene stream, deteniendo..."
            )
            self.streams[camera_id].stop()

        stream = CameraAudioStream(ip=ip, port=port, volume=volume)
        if stream.start():
            self.streams[camera_id] = stream
            logger.info(
                f"✅ [manager] Audio cámara {camera_id} activo "
                f"({len(self.streams)} stream(s) total(es))"
            )
            return True

        logger.error(f"❌ [manager] No se pudo iniciar audio para cámara {camera_id}")
        return False

    def start_local_audio(self, volume: float = 0.7) -> bool:
        logger.debug(f"🔊 [manager] start_local_audio: volume={volume}")

        if -1 in self.streams:
            logger.debug("🔊 [manager] Micrófono ya activo, deteniendo...")
            self.streams[-1].stop()

        stream = LocalAudioStream(volume=volume)
        if stream.start():
            self.streams[-1] = stream
            logger.info(
                f"✅ [manager] Micrófono activo "
                f"({len(self.streams)} stream(s) total(es))"
            )
            return True

        logger.error("❌ [manager] No se pudo iniciar micrófono")
        return False

    def stop_camera_audio(self, camera_id: int):
        if camera_id in self.streams:
            logger.debug(f"🔊 [manager] Deteniendo audio cámara {camera_id}")
            self.streams[camera_id].stop()
            del self.streams[camera_id]
            logger.debug(
                f"🔊 [manager] Quedan {len(self.streams)} stream(s)"
            )

    def stop_local_audio(self):
        if -1 in self.streams:
            logger.debug("🔊 [manager] Deteniendo micrófono local")
            self.streams[-1].stop()
            del self.streams[-1]
            logger.debug(
                f"🔊 [manager] Quedan {len(self.streams)} stream(s)"
            )

    def stop_all(self):
        logger.debug(
            f"🔊 [manager] stop_all: {len(self.streams)} stream(s) activos"
        )
        for camera_id in list(self.streams.keys()):
            try:
                self.streams[camera_id].stop()
            except Exception as e:
                logger.debug(f"🔊 [manager] Error deteniendo {camera_id}: {e}")
        self.streams.clear()
        logger.info("🔇 Todo el audio detenido")

    def is_camera_audio_active(self, camera_id: int) -> bool:
        return camera_id in self.streams and self.streams[camera_id].is_running()

    def is_local_audio_active(self) -> bool:
        return -1 in self.streams and self.streams[-1].is_running()

    def set_volume(self, camera_id: int, volume: float):
        if camera_id in self.streams:
            self.streams[camera_id].set_volume(volume)
            logger.debug(
                f"🔊 [manager] Volumen cámara {camera_id}: {volume}"
            )

    # ✅ NUEVO: Mute / Unmute
    def set_muted(self, camera_id: int, muted: bool):
        """Mutea/desmutea el audio de una cámara (o micrófono con id=-1)."""
        if camera_id in self.streams:
            self.streams[camera_id].set_muted(muted)
            logger.debug(
                f"🔊 [manager] Cámara {camera_id} mute={muted}"
            )
        else:
            logger.debug(
                f"🔊 [manager] No hay stream para {camera_id}, mute ignorado"
            )

    def is_muted(self, camera_id: int) -> bool:
        if camera_id in self.streams:
            return self.streams[camera_id].is_muted()
        return False

    def toggle_mute(self, camera_id: int) -> bool:
        """Alterna el mute. Retorna el nuevo estado."""
        if camera_id in self.streams:
            new_state = not self.streams[camera_id].is_muted()
            self.streams[camera_id].set_muted(new_state)
            return new_state
        return False


# Singleton global
audio_manager = AudioManager()