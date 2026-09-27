"""
Escritor WAV en paralelo para grabación de audio.

El plugin de audio lo usa para escribir el stream de audio a un .wav
mientras el Core graba el video. Al detener, se mezclan con ffmpeg.

Por qué WAV (y no codificar a AAC en tiempo real):
  - Escritura es I/O simple (no codificación).
  - CPU casi 0% durante la grabación (clave en PCs de bajos recursos).
  - Se codifica UNA vez al final con ffmpeg -c:v copy (segundos).
"""
import os
import wave
import threading
from typing import Optional

from utils.logger import get_logger

logger = get_logger("Plugin.AudioWavWriter")


class WavWriter:
    """
    Escribe un stream de audio PCM a un archivo WAV.

    Thread-safe: el callback de audio puede escribir desde otro hilo.
    """

    def __init__(self, path: str, sample_rate: int = 44100,
                 channels: int = 1, sample_width: int = 2):
        self.path = path
        self.sample_rate = sample_rate
        self.channels = channels
        self.sample_width = sample_width

        self._wf: Optional[wave.Wave_write] = None
        self._lock = threading.Lock()
        self._is_open = False
        self._bytes_written = 0

    def open(self) -> bool:
        """Abre el archivo para escritura."""
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            self._wf = wave.open(self.path, 'wb')
            self._wf.setnchannels(self.channels)
            self._wf.setsampwidth(self.sample_width)
            self._wf.setframerate(self.sample_rate)
            self._is_open = True
            logger.debug(
                f"🎙️ [wav] Abierto: {self.path} "
                f"({self.sample_rate}Hz, {self.channels}ch, {self.sample_width*8}bit)"
            )
            return True
        except Exception as e:
            logger.error(f"❌ Error abriendo WAV: {e}", exc_info=True)
            self._is_open = False
            return False

    def write(self, pcm_bytes: bytes):
        """Escribe bytes PCM (int16, little-endian)."""
        if not self._is_open or not self._wf:
            return
        with self._lock:
            try:
                self._wf.writeframes(pcm_bytes)
                self._bytes_written += len(pcm_bytes)
            except Exception as e:
                logger.debug(f"Error escribiendo WAV: {e}")

    def close(self) -> Optional[str]:
        """Cierra el archivo. Retorna la ruta si se escribió algo."""
        with self._lock:
            if not self._is_open or not self._wf:
                return None
            try:
                self._wf.close()
            except Exception as e:
                logger.debug(f"Error cerrando WAV: {e}")
            self._is_open = False
            self._wf = None

        if self._bytes_written > 0:
            logger.info(
                f"🎙️ [wav] Cerrado: {self.path} "
                f"({self._bytes_written / 1024:.1f} KB)"
            )
            return self.path
        else:
            logger.debug("🎙️ [wav] Cerrado sin datos")
            try:
                os.remove(self.path)
            except Exception:
                pass
            return None

    def is_open(self) -> bool:
        return self._is_open

    def get_bytes_written(self) -> int:
        return self._bytes_written