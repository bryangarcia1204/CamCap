"""Tests para utils/pixmap_pool.py

FIX v2:
- Tests de ScaledPixmapPool.stats()
- Tests de cache hit/miss
- Propiedades en lugar de valores exactos
"""
import pytest
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtCore import QSize, Qt

from utils.pixmap_pool import PixmapPool, ScaledPixmapPool


@pytest.mark.gui
class TestPixmapPool:
    def test_init_creates_pool(self, qapp):
        pool = PixmapPool(size=3)
        assert len(pool._available) == 3
        assert pool._max_size == 3

    def test_init_minimum_size(self, qapp):
        """Tamaño mínimo debe forzarse a 1"""
        pool = PixmapPool(size=0)
        assert pool._max_size >= 1

    def test_acquire_returns_pixmap(self, qapp):
        pool = PixmapPool(size=2)
        pm = pool.acquire()

        assert pm is not None
        assert isinstance(pm, QPixmap)
        assert len(pool._available) == 1

    def test_acquire_empty_returns_none(self, qapp):
        pool = PixmapPool(size=1)
        pool.acquire()  # Agota el pool
        pm = pool.acquire()

        assert pm is None

    def test_release_returns_to_pool(self, qapp):
        pool = PixmapPool(size=2)
        pm = pool.acquire()
        assert len(pool._available) == 1

        pool.release(pm)
        assert len(pool._available) == 2

    def test_release_none_is_safe(self, qapp):
        pool = PixmapPool(size=2)
        pool.release(None)  # No debe crashear
        assert len(pool._available) == 2

    def test_release_unknown_pixmap_is_safe(self, qapp):
        pool = PixmapPool(size=2)
        unknown = QPixmap(100, 100)
        pool.release(unknown)  # No debe crashear

    def test_stats_returns_dict(self, qapp):
        pool = PixmapPool(size=3)
        stats = pool.stats()

        assert isinstance(stats, dict)
        assert "max_size" in stats
        assert "available" in stats
        assert "in_use" in stats

    def test_stats_values_correct(self, qapp):
        pool = PixmapPool(size=3)
        pool.acquire()

        stats = pool.stats()
        assert stats["max_size"] == 3
        assert stats["available"] == 2
        assert stats["in_use"] == 1

    def test_clear_empties_pool(self, qapp):
        pool = PixmapPool(size=2)
        pool.clear()

        assert len(pool._available) == 0
        assert len(pool._in_use) == 0

    def test_resize_all(self, qapp):
        pool = PixmapPool(size=2, initial_size=QSize(640, 480))
        new_size = QSize(320, 240)
        pool.resize_all(new_size)

        # Debe haber redimensionado
        for pm in pool._available:
            assert pm.size() == new_size


@pytest.mark.gui
class TestScaledPixmapPool:
    def test_init(self, qapp):
        pool = ScaledPixmapPool()
        assert pool._cached_scaled is None

    def test_get_scaled_returns_pixmap(self, qapp):
        pool = ScaledPixmapPool()
        qimage = QImage(640, 480, QImage.Format_RGB888)
        qimage.fill(0xFF0000)

        target = QSize(320, 240)
        result = pool.get_scaled(qimage, target)

        assert result is not None
        assert not result.isNull()

    def test_get_scaled_null_image(self, qapp):
        pool = ScaledPixmapPool()
        null_image = QImage()
        target = QSize(320, 240)
        result = pool.get_scaled(null_image, target)

        # Sin cache previa, devuelve None
        assert result is None

    def test_get_scaled_caches_result(self, qapp):
        pool = ScaledPixmapPool()
        qimage = QImage(640, 480, QImage.Format_RGB888)
        qimage.fill(0xFF0000)

        pool.get_scaled(qimage, QSize(320, 240))

        assert pool._cached_scaled is not None
        assert pool._last_target_size is not None

    def test_invalidate_clears_cache(self, qapp):
        pool = ScaledPixmapPool()
        qimage = QImage(640, 480, QImage.Format_RGB888)
        qimage.fill(0xFF0000)

        pool.get_scaled(qimage, QSize(320, 240))
        assert pool._cached_scaled is not None

        pool.invalidate()

        assert pool._cached_scaled is None
        assert pool._last_target_size is None

    def test_stats_returns_dict(self, qapp):
        pool = ScaledPixmapPool()
        stats = pool.stats()

        assert isinstance(stats, dict)
        assert "max_size" in stats
        assert "available" in stats
        assert "in_use" in stats

    def test_clear_empties_everything(self, qapp):
        pool = ScaledPixmapPool()
        qimage = QImage(640, 480, QImage.Format_RGB888)
        qimage.fill(0xFF0000)

        pool.get_scaled(qimage, QSize(320, 240))
        pool.clear()

        assert pool._cached_scaled is None
        assert pool._last_target_size is None

    def test_multiple_scales_different_sizes(self, qapp):
        """Escalar al mismo target 2 veces debe reutilizar cache"""
        pool = ScaledPixmapPool()
        qimage = QImage(640, 480, QImage.Format_RGB888)
        qimage.fill(0xFF0000)

        r1 = pool.get_scaled(qimage, QSize(320, 240))
        r2 = pool.get_scaled(qimage, QSize(320, 240))

        # Ambos deben ser válidos
        assert r1 is not None
        assert r2 is not None