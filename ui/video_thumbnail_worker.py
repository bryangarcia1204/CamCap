"""
Worker en background que genera miniaturas de video.
FIX: crash por QImage sin copia segura y array no contiguo.
Usa QThreadPool + QRunnable para no bloquear la UI.
"""
import os
import hashlib
import threading
import cv2
import numpy as np
from typing import Optional
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, QSize, Qt
from PySide6.QtGui import QImage, QPixmap
from utils.config_loader import advanced_config

from utils.logger import get_logger

logger = get_logger("VideoThumbnail")


class ThumbnailSignals(QObject):
    """Señales para el worker (QRunnable no puede tener señales directamente)"""
    thumbnail_ready = Signal(str, QImage)  # (video_path, thumbnail)
    thumbnail_failed = Signal(str, str)    # (video_path, error)


class VideoThumbnailWorker(QRunnable):
    """Worker que genera la miniatura de un video en background"""

    def __init__(self, video_path: str, size: int = 160, cache_dir: Optional[str] = None):
        super().__init__()
        self.video_path = video_path
        self.size = size
        self.cache_dir = cache_dir or self._get_default_cache_dir()

        self.signals = ThumbnailSignals()
        self.setAutoDelete(True)

    def _get_default_cache_dir(self) -> str:
        """Retorna el directorio de caché de miniaturas"""
        try:
            from PySide6.QtCore import QStandardPaths
            base = QStandardPaths.writableLocation(QStandardPaths.CacheLocation)
        except Exception:
            base = os.path.expanduser("~/.procamera_cache")

        cache_dir = os.path.join(base, "video_thumbnails")
        try:
            os.makedirs(cache_dir, exist_ok=True)
        except Exception:
            cache_dir = os.path.expanduser("~/.procamera_cache/video_thumbnails")
            os.makedirs(cache_dir, exist_ok=True)
        return cache_dir

    def _get_cache_path(self) -> str:
        """Genera un path de caché único basado en path + mtime + size"""
        try:
            mtime = os.path.getmtime(self.video_path)
            file_size = os.path.getsize(self.video_path)
        except OSError:
            mtime = 0
            file_size = 0

        key = f"{self.video_path}_{mtime}_{file_size}_{self.size}"
        hash_key = hashlib.md5(key.encode('utf-8')).hexdigest()
        
        return os.path.join(self.cache_dir, f"{hash_key}.png")

    def run(self):
        logger.debug(f"🎬 [thumb-worker] INICIO: {self.video_path}")
        try:
            cache_path = self._get_cache_path()
            if os.path.exists(cache_path):
                img = QImage(cache_path)
                if not img.isNull():
                    logger.debug(f"🎬 [thumb-worker] Cache hit: {self.video_path}")
                    self.signals.thumbnail_ready.emit(self.video_path, img)
                    return

            logger.debug(f"🎬 [thumb-worker] Generando miniatura...")
            thumbnail = self._generate_thumbnail()

            if thumbnail is None or thumbnail.isNull():
                logger.debug(f"🎬 [thumb-worker] Falló: miniatura nula")
                self.signals.thumbnail_failed.emit(self.video_path, "No se pudo generar")
                return

            try:
                thumbnail.save(cache_path, "PNG")
            except Exception as e:
                logger.debug(f"🎬 [thumb-worker] No se pudo guardar caché: {e}")

            logger.debug(f"🎬 [thumb-worker] OK: {self.video_path}")
            self.signals.thumbnail_ready.emit(self.video_path, thumbnail)

        except Exception as e:
            logger.error(f"❌ [thumb-worker] Error: {e}", exc_info=True)
            self.signals.thumbnail_failed.emit(self.video_path, str(e))

    def _generate_thumbnail(self) -> Optional[QImage]:
        """
        Extrae el frame del medio del video usando OpenCV.
        FIX: np.ascontiguousarray + .copy() inmediato para evitar segfault.
        """
        position = advanced_config.get("thumbnail_frame_position", 0.25)
        try:

            cap = cv2.VideoCapture(self.video_path)
            if not cap.isOpened():
                logger.debug(f"No se pudo abrir: {self.video_path}")
                return None

            try:
                # Ir al 25% del video (más representativo que el medio exacto)
                frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                if frame_count > 0:
                    target_frame = int(frame_count * position)
                    cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)

                ret, frame = cap.read()

                # Si falla, volver al inicio
                if not ret or frame is None:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = cap.read()

                # Si sigue fallando, intentar desde el frame 1
                if not ret or frame is None:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 1)
                    ret, frame = cap.read()

                if not ret or frame is None:
                    return None

                # === FIX: Conversión segura BGR → RGB ===
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                # ✅ Hacer el array contiguo en memoria (evita segfault)
                rgb = np.ascontiguousarray(rgb)

                h, w, ch = rgb.shape
                bytes_per_line = ch * w

                # ✅ Crear QImage y COPIAR INMEDIATAMENTE
                # Sin el .copy() aquí, el QImage apuntaría a `rgb.data`
                # que es un array local que se libera al salir de la función
                qt_image = QImage(
                    rgb.data, w, h, bytes_per_line,
                    QImage.Format_RGB888
                ).copy()  # ← CRÍTICO: copy() inmediato

                # Escalar manteniendo aspect ratio
                scaled = qt_image.scaled(
                    self.size, self.size,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )

                # ✅ Devolver una copia (por seguridad adicional)
                return scaled.copy()

            finally:
                try:
                    cap.release()
                except Exception:
                    pass

        except ImportError:
            logger.error("OpenCV no instalado, no se pueden generar miniaturas")
            return None
        except Exception as e:
            logger.error(f"Error en _generate_thumbnail: {e}", exc_info=True)
            return None


class VideoThumbnailManager:
    """
    Gestor singleton que coordina los workers de miniaturas.
    Cachea los QImage ya generados para no regenerar.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        self.thread_pool = QThreadPool()
        workers = advanced_config.get("video_thumbnail_workers", 2)
        self.thread_pool.setMaxThreadCount(workers)  # ← NUEVO

        # Caché en memoria: video_path -> QImage
        self._cache: dict = {}
        self._pending: set = set()
        self._cache_lock = None  # Se inicializa lazy

        logger.info("🎬 VideoThumbnailManager inicializado")

    def _ensure_lock(self):
        """Inicializa el lock de forma lazy (debe ser en el hilo GUI)"""
        if self._cache_lock is None:
            self._cache_lock = threading.Lock()

    def get_thumbnail_async(self, video_path: str, callback, size: int = 160):
        """
        Obtiene (o genera) la miniatura de un video de forma asíncrona.

        Args:
            video_path: Ruta al video
            callback: función que recibe (video_path, QImage)
            size: tamaño de la miniatura en píxeles
        """
        self._ensure_lock()

        # Si ya está en caché, devolver inmediatamente
        with self._cache_lock:
            if video_path in self._cache:
                cached = self._cache[video_path]
                callback(video_path, cached)
                return

            # Si ya está pendiente, no hacer nada
            if video_path in self._pending:
                return

            self._pending.add(video_path)

        worker = VideoThumbnailWorker(video_path, size)
        worker.signals.thumbnail_ready.connect(
            lambda path, img: self._on_thumbnail_ready(path, img, callback)
        )
        worker.signals.thumbnail_failed.connect(
            lambda path, err: self._on_thumbnail_failed(path, err, callback)
        )

        self.thread_pool.start(worker)

    def _on_thumbnail_ready(self, video_path: str, image: QImage, callback):
        with self._cache_lock:
            self._cache[video_path] = image
            self._pending.discard(video_path)
        try:
            callback(video_path, image)
        except Exception as e:
            logger.debug(f"Error en callback de thumbnail: {e}")

    def _on_thumbnail_failed(self, video_path: str, error: str, callback):
        with self._cache_lock:
            self._pending.discard(video_path)
        try:
            callback(video_path, None)
        except Exception as e:
            logger.debug(f"Error en callback de thumbnail fallido: {e}")

    def clear_cache(self):
        """Limpia la caché en memoria"""
        self._ensure_lock()
        with self._cache_lock:
            self._cache.clear()
        logger.info("🗑️ Caché de miniaturas limpiada")

    def cleanup(self):
        """Limpia recursos al cerrar la app"""
        try:
            self.thread_pool.clear()
            self.thread_pool.waitForDone(2000)
        except Exception:
            pass
        self.clear_cache()


# Instancia global
video_thumbnail_manager = VideoThumbnailManager()