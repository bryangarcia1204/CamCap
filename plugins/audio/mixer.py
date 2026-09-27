"""
Mezclador de video + audio.

Estrategia:
  1. Si ffmpeg está disponible → 1 comando rápido (`-c:v copy`).
  2. Si no → PyAV (remux, sin recodificar video).

CPU: prácticamente 0 durante la mezcla (copia de streams).
"""
import os
import shutil
import subprocess
from typing import Optional

from utils.logger import get_logger

logger = get_logger("Plugin.AudioMixer")


def _find_ffmpeg() -> Optional[str]:
    """Busca ffmpeg en PATH o en ubicaciones comunes."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg

    common = [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
    ]
    for p in common:
        if os.path.isfile(p):
            return p
    return None


class AudioMixer:
    """Mezcla video y audio en un solo archivo."""

    def __init__(self):
        self._ffmpeg = _find_ffmpeg()
        if self._ffmpeg:
            logger.info(f"✅ ffmpeg detectado: {self._ffmpeg}")
        else:
            logger.warning("⚠️ ffmpeg no encontrado, se usará PyAV (más lento)")

    def is_ffmpeg_available(self) -> bool:
        return self._ffmpeg is not None

    def mix(self, video_path: str, audio_path: str,
            output_path: str = None, delete_sources: bool = True) -> Optional[str]:
        """
        Mezcla video + audio en output_path.

        Args:
            video_path: ruta del .mp4 sin audio
            audio_path: ruta del .wav con audio
            output_path: ruta de salida. Si None, sobreescribe video_path.
            delete_sources: borra video_path y audio_path al terminar.

        Returns:
            Ruta del archivo final, o None si falló.
        """
        if not os.path.isfile(video_path):
            logger.error(f"❌ Video no existe: {video_path}")
            return None
        if not os.path.isfile(audio_path):
            logger.warning(f"⚠️ Audio no existe: {audio_path}, devolviendo video original")
            return video_path

        if output_path is None:
            output_path = video_path

        # Usar un temporal si sobreescribimos el video
        temp_output = None
        if os.path.abspath(output_path) == os.path.abspath(video_path):
            temp_output = video_path + ".muxing.mp4"
            target = temp_output
        else:
            target = output_path

        success = False
        if self._ffmpeg:
            success = self._mix_ffmpeg(video_path, audio_path, target)
        else:
            success = self._mix_pyav(video_path, audio_path, target)

        if not success:
            if temp_output and os.path.exists(temp_output):
                try:
                    os.remove(temp_output)
                except Exception:
                    pass
            logger.error("❌ Mezcla falló")
            return video_path

        # Mover temporal a destino
        if temp_output:
            try:
                if os.path.exists(output_path):
                    os.remove(output_path)
                shutil.move(temp_output, output_path)
            except Exception as e:
                logger.error(f"❌ Error moviendo mezcla: {e}")
                return video_path

        # Limpiar fuentes
        if delete_sources:
            try:
                if os.path.abspath(audio_path) != os.path.abspath(output_path):
                    os.remove(audio_path)
            except Exception:
                pass

        size = os.path.getsize(output_path)
        logger.info(
            f"🎬 Mezcla completada: {output_path} "
            f"({size / 1024 / 1024:.1f} MB)"
        )
        return output_path

    # ==================== BACKENDS ====================

    def _mix_ffmpeg(self, video: str, audio: str, output: str) -> bool:
        """Mezcla rápida con ffmpeg. Copia el stream de video (sin recodificar)."""
        try:
            cmd = [
                self._ffmpeg,
                "-y",
                "-i", video,
                "-i", audio,
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "128k",
                "-shortest",
                output,
            ]
            logger.debug(f"🎬 Ejecutando: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=120,
            )
            if result.returncode != 0:
                logger.error(
                    f"❌ ffmpeg falló (code {result.returncode}): "
                    f"{result.stderr.decode('utf-8', errors='ignore')[:500]}"
                )
                return False
            return True
        except subprocess.TimeoutExpired:
            logger.error("❌ ffmpeg timeout")
            return False
        except Exception as e:
            logger.error(f"❌ Error ejecutando ffmpeg: {e}", exc_info=True)
            return False

    def _mix_pyav(self, video: str, audio: str, output: str) -> bool:
        """Mezcla con PyAV (fallback sin ffmpeg). Lento pero funcional."""
        try:
            import av
        except ImportError:
            logger.error("❌ PyAV no instalado y ffmpeg no disponible")
            return False

        try:
            input_video = av.open(video)
            input_audio = av.open(audio)
            output_container = av.open(output, mode='w')

            v_in = input_video.streams.video[0]
            a_in = input_audio.streams.audio[0]

            v_out = output_container.add_stream(template=v_in)
            a_out = output_container.add_stream(template=a_in)

            # Copiar video
            for packet in input_video.demux(v_in):
                if packet.dts is None:
                    continue
                packet.stream = v_out
                output_container.mux(packet)

            # Copiar audio
            for packet in input_audio.demux(a_in):
                if packet.dts is None:
                    continue
                packet.stream = a_out
                output_container.mux(packet)

            output_container.close()
            input_video.close()
            input_audio.close()
            return True

        except Exception as e:
            logger.error(f"❌ Error en mezcla PyAV: {e}", exc_info=True)
            return False