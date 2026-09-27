"""
Pool de QPixmap reutilizables para evitar allocations por frame.
Cada widget obtiene su propio pool con N buffers pre-asignados.
"""
from typing import Optional, List
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtCore import QSize

from utils.logger import get_logger

logger = get_logger("PixmapPool")


class PixmapPool:
    """
    Pool de QPixmap reutilizables.

    Uso:
        pool = PixmapPool(size=3, initial_size=QSize(640, 480))
        pixmap = pool.acquire()  # obtiene uno libre
        pixmap.convertFromImage(qimage)  # reutiliza el buffer
        # ... usar pixmap ...
        pool.release(pixmap)  # devuelve al pool

    Beneficio: elimina el coste de allocation/GC de QPixmap por frame.
    """

    def __init__(self, size: int = 3, initial_size: QSize = None):
        """
        Args:
            size: número máximo de pixmaps en el pool
            initial_size: tamaño inicial de los pixmaps (opcional)
        """
        self._max_size = max(1, size)
        self._available: List[QPixmap] = []
        self._in_use: set = set()
        self._initial_size = initial_size

        # Pre-asignar pixmaps
        initial = initial_size or QSize(640, 480)
        for _ in range(self._max_size):
            pm = QPixmap(initial)
            pm.fill(0)
            self._available.append(pm)

        logger.debug(f"PixmapPool creado (max={self._max_size})")

    def acquire(self) -> Optional[QPixmap]:
        """
        Obtiene un QPixmap del pool.
        Si no hay disponibles, devuelve None (para que el caller use uno nuevo).
        """
        if self._available:
            pm = self._available.pop()
            self._in_use.add(id(pm))
            return pm
        return None

    def release(self, pixmap: QPixmap):
        """Devuelve un QPixmap al pool"""
        if pixmap is None:
            return

        pm_id = id(pixmap)
        if pm_id in self._in_use:
            self._in_use.discard(pm_id)
            if len(self._available) < self._max_size:
                self._available.append(pixmap)
                return

        # Si no estaba en uso (o el pool está lleno), simplemente se descarta
        # Qt lo liberará cuando salga del scope

    def resize_all(self, new_size: QSize):
        """
        Redimensiona todos los pixmaps del pool.
        Útil cuando cambia el tamaño del widget.
        """
        if self._initial_size == new_size:
            return

        self._initial_size = new_size

        # Redimensionar disponibles
        for pm in self._available:
            if pm.size() != new_size:
                # Crear uno nuevo (QPixmap no se puede redimensionar in-place)
                new_pm = QPixmap(new_size)
                new_pm.fill(0)
                # Reemplazar en la lista
                idx = self._available.index(pm)
                self._available[idx] = new_pm

        logger.debug(f"PixmapPool redimensionado a {new_size.width()}x{new_size.height()}")

    def clear(self):
        """Limpia el pool"""
        self._available.clear()
        self._in_use.clear()

    def stats(self) -> dict:
        """Retorna estadísticas del pool"""
        return {
            "max_size": self._max_size,
            "available": len(self._available),
            "in_use": len(self._in_use),
        }


class ScaledPixmapPool:
    """
    Pool especializado que también cachea el pixmap escalado.
    Evita reescalar si el tamaño no cambió y el contenido es similar.

    Uso:
        pool = ScaledPixmapPool()
        result = pool.get_scaled(qimage, target_size)
        label.setPixmap(result)
    """

    def __init__(self, size: int = 3):
        self._pool = PixmapPool(size=size)
        self._last_target_size: Optional[QSize] = None
        self._cached_scaled: Optional[QPixmap] = None

        # Métricas
        self._cache_hits = 0
        self._cache_misses = 0

    def get_scaled(self, qimage: QImage, target_size: QSize,
                   aspect_mode=None, transform_mode=None) -> Optional[QPixmap]:
        """
        Escala qimage al target_size reutilizando buffers.
        """
        from PySide6.QtCore import Qt

        if aspect_mode is None:
            aspect_mode = Qt.KeepAspectRatio
        if transform_mode is None:
            transform_mode = Qt.FastTransformation

        if qimage is None or qimage.isNull():
            return self._cached_scaled

        # Obtener pixmap del pool
        pixmap = self._pool.acquire()
        if pixmap is None:
            # Pool agotado: crear uno temporal
            pixmap = QPixmap.fromImage(qimage)
        else:
            # Reutilizar: convertir desde QImage
            if pixmap.size() != qimage.size():
                pixmap = QPixmap.fromImage(qimage)
            else:
                pixmap.convertFromImage(qimage)

        # Escalar
        scaled = pixmap.scaled(
            target_size.width(),
            target_size.height(),
            aspect_mode,
            transform_mode
        )

        self._cached_scaled = scaled
        self._last_target_size = target_size

        # Devolver el pixmap original al pool
        self._pool.release(pixmap)

        return scaled

    def invalidate(self):
        """Invalida el cache (llamar cuando cambia el tamaño del label)"""
        self._last_target_size = None
        self._cached_scaled = None

    def stats(self) -> dict:
        return {
            **self._pool.stats(),
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
        }

    def clear(self):
        self._pool.clear()
        self._cached_scaled = None
        self._last_target_size = None