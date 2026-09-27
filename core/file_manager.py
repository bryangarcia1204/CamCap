"""
Gestión de archivos con soporte Unicode completo
"""
import os
import cv2
import numpy as np
import tempfile
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Tuple, Optional

from core.models import ImageFormat, VideoFormat, CaptureSettings
from utils.logger import get_logger

logger = get_logger("FileManager")


class FileManager:
    """Maneja guardado de imágenes y videos con formatos configurables"""

    def __init__(self, settings: CaptureSettings):
        self.settings = settings
        self._scan_manager = None

        # Interpolación (desde config)
        from utils.config_loader import advanced_config
        cfg = advanced_config.get_all()
        self.image_interpolation = cfg.get("image_interpolation", "linear")
        self.video_interpolation = cfg.get("video_interpolation", "linear")

        # Mapa de interpolaciones
        import cv2
        self._INTERPOLATION_MAP = {
            "nearest": cv2.INTER_NEAREST,
            "linear": cv2.INTER_LINEAR,
            "cubic": cv2.INTER_CUBIC,
            "area": cv2.INTER_AREA,
            "lanczos4": cv2.INTER_LANCZOS4,
        }

        # 🔍 DEBUG: Estado inicial
        logger.debug(
            f"🔧 [init] FileManager: img_interp={self.image_interpolation}, "
            f"vid_interp={self.video_interpolation}"
        )

    def _get_interpolation(self, name: str):
        """Mapea string a constante de OpenCV"""
        return self._INTERPOLATION_MAP.get(name, cv2.INTER_LINEAR)

    def reload_config(self):
        """Recarga la config"""
        from utils.config_loader import advanced_config
        advanced_config.reload()
        cfg = advanced_config.get_all()

        old_img = self.image_interpolation
        old_vid = self.video_interpolation
        self.image_interpolation = cfg.get("image_interpolation", "linear")
        self.video_interpolation = cfg.get("video_interpolation", "linear")

        # 🔍 DEBUG: Cambio de config
        logger.debug(
            f"🔄 [reload] FileManager: "
            f"img={old_img}→{self.image_interpolation}, "
            f"vid={old_vid}→{self.video_interpolation}"
        )
        logger.info(f"🔄 FileManager recargado")
        return True

    def _get_scan_manager(self):
        """Lazy loading del ScanManager"""
        if self._scan_manager is None:
            try:
                from detection.scan_manager import ScanManager
                self._scan_manager = ScanManager()
            except Exception as e:
                logger.warning(f"No se pudo cargar ScanManager: {e}")
                self._scan_manager = False
        return self._scan_manager if self._scan_manager else None

    def ensure_directory(self, directory: str) -> str:
        """Asegura que el directorio existe"""
        expanded_path = os.path.expanduser(directory)
        Path(expanded_path).mkdir(parents=True, exist_ok=True)
        return expanded_path

    def generate_filename(self, base_name: str, camera_name: str, extension: str) -> str:
        """Genera nombre de archivo con variables"""
        timestamp = datetime.now()
        variables = {
            "{timestamp}": timestamp.strftime("%Y%m%d_%H%M%S"),
            "{date}": timestamp.strftime("%Y%m%d"),
            "{time}": timestamp.strftime("%H%M%S"),
            "{camera_name}": camera_name,
            "{datetime}": timestamp.strftime("%Y-%m-%d_%H-%M-%S")
        }

        filename = base_name
        for var, value in variables.items():
            filename = filename.replace(var, value)

        # Eliminar caracteres inválidos
        invalid_chars = '<>:"/\\|?*'
        filename = "".join(c if c not in invalid_chars else "_" for c in filename)
        return f"{filename}{extension}"

    def save_image(self, frame: np.ndarray, directory: str,
                   filename: str, format: ImageFormat, quality: int,
                   resolution) -> Tuple[str, int]:
        """Guarda imagen con formato, calidad y resolución configurados"""
        t0 = time.perf_counter()
        try:
            # 🔍 DEBUG: Inicio
            logger.debug(
                f"📸 [save_img] Iniciando: dir={directory}, filename={filename}, "
                f"format={format.value}, quality={quality}, "
                f"target={resolution.get_size()}, shape={frame.shape}"
            )

            # Redimensionar si es necesario
            target_width, target_height = resolution.width, resolution.height
            h, w = frame.shape[:2]

            if w != target_width or h != target_height:
                frame_resized = cv2.resize(
                            frame,
                            (target_width, target_height),
                            interpolation=self._get_interpolation(self.image_interpolation)
                        )
                # 🔍 DEBUG: Resize
                logger.debug(
                    f"📸 [save_img] Resize: {w}x{h} → {target_width}x{target_height} "
                    f"(interp={self.image_interpolation})"
                )
            else:
                frame_resized = frame

            full_dir = self.ensure_directory(directory)
            extension = f".{format.value}"
            full_path = os.path.join(full_dir, f"{filename}{extension}")

            # Parámetros según formato
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

            # Codificar y escribir con soporte Unicode
            success, buffer = cv2.imencode(extension, frame_resized, params)

            # 🔍 DEBUG: Resultado de imencode
            logger.debug(
                f"📸 [save_img] imencode: success={success}, "
                f"buffer_size={len(buffer) if success else 0}, params={params}"
            )

            if not success:
                logger.error(
                    f"❌ [save_img] cv2.imencode FALLÓ: ext={extension}, "
                    f"shape={frame_resized.shape}, params={params}"
                )
                raise Exception("Error codificando imagen")

            with open(full_path, 'wb') as f:
                f.write(buffer.tobytes())

            if not os.path.exists(full_path):
                logger.error(f"❌ [save_img] Archivo NO existe tras escribir: {full_path}")
                raise Exception(f"No se creó el archivo: {full_path}")

            size = os.path.getsize(full_path)
            elapsed_ms = (time.perf_counter() - t0) * 1000

            # 🔍 DEBUG: Éxito
            logger.debug(
                f"📸 [save_img] OK: {full_path} "
                f"({size/1024:.1f} KB, {elapsed_ms:.0f}ms)"
            )
            logger.info(f"📸 Imagen guardada: {full_path} ({size/1024:.1f} KB)")
            return full_path, size

        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            # 🔍 DEBUG: Fallo
            logger.error(
                f"❌ [save_img] FALLÓ en {elapsed_ms:.0f}ms: "
                f"{type(e).__name__}: {e}\n"
                f"   dir={directory}, filename={filename}, "
                f"format={format.value}, quality={quality}",
                exc_info=True
            )
            raise

    def save_video_from_frames(self, frames: list, output_path: str,
                                codec: str, fps: int, resolution,
                                quality: int = 80) -> Tuple[str, int]:
        """Guarda video desde lista de frames con soporte Unicode"""
        temp_path = None
        t0 = time.perf_counter()

        try:
            # 🔍 DEBUG: Inicio
            logger.debug(
                f"🎬 [save_vid] Iniciando: path={output_path}, "
                f"frames={len(frames)}, codec={codec}, fps={fps}, "
                f"target={resolution.get_size()}, quality={quality}"
            )

            full_dir = os.path.dirname(output_path)
            if full_dir:
                self.ensure_directory(full_dir)

            if not frames:
                logger.error("❌ [save_vid] No hay frames para guardar")
                raise Exception("No hay frames para guardar")

            target_width, target_height = resolution.width, resolution.height
            extension = os.path.splitext(output_path)[1]

            # Crear archivo temporal en ASCII
            temp_dir = tempfile.gettempdir()
            temp_filename = f"procamara_temp_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{extension}"
            temp_path = os.path.join(temp_dir, temp_filename)

            # 🔍 DEBUG: Temp path
            logger.debug(f"🎬 [save_vid] temp_path={temp_path}")

            fourcc = cv2.VideoWriter_fourcc(*codec)
            out = cv2.VideoWriter(
                temp_path, fourcc, fps,
                (target_width, target_height)
            )

            # 🔍 DEBUG: Writer creado
            logger.debug(
                f"🎬 [save_vid] VideoWriter: isOpened={out.isOpened()}, "
                f"fourcc={fourcc}"
            )

            if not out.isOpened():
                logger.error(
                    f"❌ [save_vid] VideoWriter no abrió: "
                    f"codec={codec}, fps={fps}, size=({target_width},{target_height})"
                )
                raise Exception("Error abriendo VideoWriter temporal")

            # Escribir frames
            frame_count = 0
            resize_count = 0
            for frame in frames:
                if frame is None:
                    continue

                h, w = frame.shape[:2]
                if w != target_width or h != target_height:
                    frame = cv2.resize(
                            frame,
                            (target_width, target_height),
                            interpolation=self._get_interpolation(self.video_interpolation)
                        )
                    resize_count += 1

                out.write(frame)
                frame_count += 1

                # 🔍 DEBUG: Cada 30 frames
                if frame_count % 30 == 0:
                    logger.debug(f"🎬 [save_vid] {frame_count}/{len(frames)} frames escritos")

            out.release()

            # 🔍 DEBUG: Resumen de escritura
            logger.debug(
                f"🎬 [save_vid] Escritura completada: {frame_count} frames "
                f"(resize={resize_count}, interp={self.video_interpolation})"
            )

            if not os.path.exists(temp_path):
                logger.error(f"❌ [save_vid] Temp NO existe: {temp_path}")
                raise Exception("Archivo temporal no creado")

            # Mover a destino final
            if os.path.exists(output_path):
                os.remove(output_path)

            shutil.move(temp_path, output_path)
            temp_path = None

            if not os.path.exists(output_path):
                logger.error(f"❌ [save_vid] Destino NO existe tras move: {output_path}")
                raise Exception("Archivo final no existe")

            size = os.path.getsize(output_path)
            elapsed_ms = (time.perf_counter() - t0) * 1000

            # 🔍 DEBUG: Éxito
            logger.debug(
                f"🎬 [save_vid] OK: {output_path} "
                f"({frame_count} frames, {size/1024/1024:.1f} MB, {elapsed_ms:.0f}ms)"
            )
            logger.info(f"🎬 Video guardado: {output_path} ({frame_count} frames, {size/1024/1024:.1f} MB)")
            return output_path, size

        except Exception as e:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
            elapsed_ms = (time.perf_counter() - t0) * 1000
            # 🔍 DEBUG: Fallo
            logger.error(
                f"❌ [save_vid] FALLÓ en {elapsed_ms:.0f}ms: "
                f"{type(e).__name__}: {e}",
                exc_info=True
            )
            raise

    def get_capture_info(self, file_path: str) -> dict:
        """Obtiene información de archivo con soporte Unicode"""
        if not os.path.exists(file_path):
            # 🔍 DEBUG: Archivo no existe
            logger.debug(f"⚠️ [info] Archivo no existe: {file_path}")
            return {}

        info = {
            "path": file_path,
            "filename": os.path.basename(file_path),
            "size": os.path.getsize(file_path),
            "created": datetime.fromtimestamp(os.path.getctime(file_path))
        }

        ext = os.path.splitext(file_path)[1].lower()

        # Imágenes
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
                        "format": ext[1:].upper()
                    })
                    # 🔍 DEBUG: Imagen decodificada
                    logger.debug(
                        f"🖼️ [info] {info['filename']}: "
                        f"{info['width']}x{info['height']} ({info['format']})"
                    )
                else:
                    logger.debug(f"⚠️ [info] cv2.imdecode devolvió None: {file_path}")
            except Exception as e:
                logger.error(f"Error leyendo imagen: {e}")

        # Videos
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
                        "format": ext[1:].upper()
                    })
                    cap.release()

                    # 🔍 DEBUG: Video decodificado
                    logger.debug(
                        f"🎬 [info] {info['filename']}: "
                        f"{info['width']}x{info['height']} @ {fps:.1f}fps, "
                        f"{frames} frames, {info['duration']}s"
                    )
                else:
                    logger.debug(f"⚠️ [info] VideoCapture no abrió: {file_path}")
            except Exception as e:
                logger.error(f"Error leyendo video: {e}")

        return info