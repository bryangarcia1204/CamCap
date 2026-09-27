"""
Gestión de archivos con soporte Unicode completo.

El FileManager NO conoce plugins. Emite eventos (IMAGE_SAVED, VIDEO_SAVED)
para que cualquiera (plugin de OCR, cloud sync, etc.) reaccione.
"""
import os
import cv2
import numpy as np
import tempfile
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Tuple

from core.models import ImageFormat, VideoFormat, CaptureSettings
from core.event_bus import get_event_bus
from core.events import IMAGE_SAVED, VIDEO_SAVED
from utils.logger import get_logger

logger = get_logger("FileManager")


class FileManager:
    """Maneja guardado de imágenes y videos con formatos configurables."""

    def __init__(self, settings: CaptureSettings):
        self.settings = settings

        from utils.config_loader import advanced_config
        cfg = advanced_config.get_all()
        self.image_interpolation = cfg.get("image_interpolation", "linear")
        self.video_interpolation = cfg.get("video_interpolation", "linear")

        import cv2
        self._INTERPOLATION_MAP = {
            "nearest": cv2.INTER_NEAREST,
            "linear": cv2.INTER_LINEAR,
            "cubic": cv2.INTER_CUBIC,
            "area": cv2.INTER_AREA,
            "lanczos4": cv2.INTER_LANCZOS4,
        }

        logger.debug(
            f"🔧 [init] FileManager: img_interp={self.image_interpolation}, "
            f"vid_interp={self.video_interpolation}"
        )

    def _get_interpolation(self, name: str):
        return self._INTERPOLATION_MAP.get(name, cv2.INTER_LINEAR)

    def reload_config(self):
        from utils.config_loader import advanced_config
        advanced_config.reload()
        cfg = advanced_config.get_all()

        old_img = self.image_interpolation
        old_vid = self.video_interpolation
        self.image_interpolation = cfg.get("image_interpolation", "linear")
        self.video_interpolation = cfg.get("video_interpolation", "linear")

        logger.debug(
            f"🔄 [reload] FileManager: "
            f"img={old_img}→{self.image_interpolation}, "
            f"vid={old_vid}→{self.video_interpolation}"
        )
        return True

    def ensure_directory(self, directory: str) -> str:
        expanded_path = os.path.expanduser(directory)
        Path(expanded_path).mkdir(parents=True, exist_ok=True)
        return expanded_path

    def generate_filename(self, base_name: str, camera_name: str, extension: str) -> str:
        timestamp = datetime.now()
        variables = {
            "{timestamp}": timestamp.strftime("%Y%m%d_%H%M%S"),
            "{date}": timestamp.strftime("%Y%m%d"),
            "{time}": timestamp.strftime("%H%M%S"),
            "{camera_name}": camera_name,
            "{datetime}": timestamp.strftime("%Y-%m-%d_%H-%M-%S"),
        }

        filename = base_name
        for var, value in variables.items():
            filename = filename.replace(var, value)

        invalid_chars = '<>:"/\\|?*'
        filename = "".join(c if c not in invalid_chars else "_" for c in filename)
        return f"{filename}{extension}"

    # ==================== GUARDAR IMAGEN ====================

    def save_image(self, frame: np.ndarray, directory: str,
                   filename: str, format: ImageFormat, quality: int,
                   resolution) -> Tuple[str, int]:
        """Guarda imagen. Emite IMAGE_SAVED al terminar."""
        t0 = time.perf_counter()
        try:
            logger.debug(
                f"📸 [save_img] Iniciando: dir={directory}, filename={filename}, "
                f"format={format.value}, quality={quality}, "
                f"target={resolution.get_size()}, shape={frame.shape}"
            )

            target_width, target_height = resolution.width, resolution.height
            h, w = frame.shape[:2]

            if w != target_width or h != target_height:
                frame_resized = cv2.resize(
                    frame,
                    (target_width, target_height),
                    interpolation=self._get_interpolation(self.image_interpolation),
                )
                logger.debug(
                    f"📸 [save_img] Resize: {w}x{h} → {target_width}x{target_height}"
                )
            else:
                frame_resized = frame

            full_dir = self.ensure_directory(directory)
            extension = f".{format.value}"
            full_path = os.path.join(full_dir, f"{filename}{extension}")

            params = []
            if format == ImageFormat.JPG:
                params = [cv2.IMWRITE_JPEG_QUALITY, quality]
            elif format == ImageFormat.PNG:
                compression = int((100 - quality) / 100 * 9)
                params = [cv2.IMWRITE_PNG_COMPRESSION, compression]
            elif format == ImageFormat.BMP:
                params = []
            elif format == ImageFormat.TIFF:
                params = [cv2.IMWRITE_TIFF_COMPRESSION, 1]

            success, buffer = cv2.imencode(extension, frame_resized, params)
            if not success:
                raise Exception("Error codificando imagen")

            with open(full_path, 'wb') as f:
                f.write(buffer.tobytes())

            if not os.path.exists(full_path):
                raise Exception(f"No se creó el archivo: {full_path}")

            size = os.path.getsize(full_path)
            elapsed_ms = (time.perf_counter() - t0) * 1000

            logger.info(f"📸 Imagen guardada: {full_path} ({size/1024:.1f} KB, {elapsed_ms:.0f}ms)")

            # ✅ Emitir evento (sin saber quién escucha)
            try:
                get_event_bus().emit(
                    IMAGE_SAVED,
                    path=full_path,
                    frame=frame_resized,
                    size_bytes=size,
                    format=format.value,
                )
            except Exception as e:
                logger.debug(f"Error emitiendo IMAGE_SAVED: {e}")

            return full_path, size

        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.error(
                f"❌ [save_img] FALLÓ en {elapsed_ms:.0f}ms: "
                f"{type(e).__name__}: {e}",
                exc_info=True,
            )
            raise

    # ==================== GUARDAR VIDEO ====================

    def save_video_from_frames(self, frames: list, output_path: str,
                                codec: str, fps: int, resolution,
                                quality: int = 80) -> Tuple[str, int]:
        """Guarda video desde lista de frames. Emite VIDEO_SAVED al terminar."""
        temp_path = None
        t0 = time.perf_counter()

        try:
            logger.debug(
                f"🎬 [save_vid] Iniciando: path={output_path}, "
                f"frames={len(frames)}, codec={codec}, fps={fps}"
            )

            full_dir = os.path.dirname(output_path)
            if full_dir:
                self.ensure_directory(full_dir)

            if not frames:
                raise Exception("No hay frames para guardar")

            target_width, target_height = resolution.width, resolution.height
            extension = os.path.splitext(output_path)[1]

            temp_dir = tempfile.gettempdir()
            temp_filename = f"procamara_temp_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{extension}"
            temp_path = os.path.join(temp_dir, temp_filename)

            fourcc = cv2.VideoWriter_fourcc(*codec)
            out = cv2.VideoWriter(
                temp_path, fourcc, fps,
                (target_width, target_height)
            )

            if not out.isOpened():
                raise Exception("Error abriendo VideoWriter temporal")

            frame_count = 0
            for frame in frames:
                if frame is None:
                    continue
                h, w = frame.shape[:2]
                if w != target_width or h != target_height:
                    frame = cv2.resize(
                        frame, (target_width, target_height),
                        interpolation=self._get_interpolation(self.video_interpolation),
                    )
                out.write(frame)
                frame_count += 1

            out.release()

            if not os.path.exists(temp_path):
                raise Exception("Archivo temporal no creado")

            if os.path.exists(output_path):
                os.remove(output_path)

            shutil.move(temp_path, output_path)
            temp_path = None

            if not os.path.exists(output_path):
                raise Exception("Archivo final no existe")

            size = os.path.getsize(output_path)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"🎬 Video guardado: {output_path} ({frame_count} frames, {size/1024/1024:.1f} MB)")

            # ✅ Emitir evento
            try:
                get_event_bus().emit(
                    VIDEO_SAVED,
                    path=output_path,
                    size_bytes=size,
                    frames=frame_count,
                    fps=fps,
                )
            except Exception as e:
                logger.debug(f"Error emitiendo VIDEO_SAVED: {e}")

            return output_path, size

        except Exception as e:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.error(
                f"❌ [save_vid] FALLÓ en {elapsed_ms:.0f}ms: "
                f"{type(e).__name__}: {e}",
                exc_info=True,
            )
            raise

    def get_capture_info(self, file_path: str) -> dict:
        """Información de archivo con soporte Unicode."""
        if not os.path.exists(file_path):
            return {}

        info = {
            "path": file_path,
            "filename": os.path.basename(file_path),
            "size": os.path.getsize(file_path),
            "created": datetime.fromtimestamp(os.path.getctime(file_path)),
        }

        ext = os.path.splitext(file_path)[1].lower()

        if ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']:
            try:
                with open(file_path, 'rb') as f:
                    data = f.read()
                arr = np.frombuffer(data, dtype=np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if img is not None:
                    info.update({
                        "type": "image",
                        "width": img.shape[1],
                        "height": img.shape[0],
                        "channels": img.shape[2] if len(img.shape) > 2 else 1,
                        "format": ext[1:].upper(),
                    })
            except Exception as e:
                logger.error(f"Error leyendo imagen: {e}")

        elif ext in ['.mp4', '.mkv', '.avi', '.mov', '.mpg']:
            try:
                cap = cv2.VideoCapture(file_path)
                if cap.isOpened():
                    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    info.update({
                        "type": "video",
                        "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                        "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                        "fps": fps,
                        "frames": frames,
                        "duration": int(frames / max(1, fps)),
                        "format": ext[1:].upper(),
                    })
                    cap.release()
            except Exception as e:
                logger.error(f"Error leyendo video: {e}")

        return info