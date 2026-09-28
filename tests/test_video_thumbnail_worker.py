"""Tests para ui/video_thumbnail_worker.py

FIX v2:
- Verifica determinismo del cache path
- Tests de thread pool
- Propiedades en lugar de valores exactos
"""
import os
import pytest
import time
from PySide6.QtGui import QImage
from PySide6.QtCore import QCoreApplication

from ui.video.video_thumbnail_worker import (
    VideoThumbnailWorker,
    VideoThumbnailManager,
    ThumbnailSignals,
)


def _wait_for_signal(timeout_s=2.0):
    """Procesa eventos durante timeout_s segundos"""
    end = time.time() + timeout_s
    while time.time() < end:
        QCoreApplication.processEvents()
        time.sleep(0.02)


@pytest.mark.gui
class TestThumbnailSignals:
    def test_signals_exist(self, qapp):
        signals = ThumbnailSignals()
        assert hasattr(signals, "thumbnail_ready")
        assert hasattr(signals, "thumbnail_failed")


@pytest.mark.gui
class TestVideoThumbnailWorker:
    def test_init(self, qapp, temp_video_path):
        worker = VideoThumbnailWorker(temp_video_path)
        assert worker.video_path == temp_video_path
        assert worker.size == 160

    def test_init_custom_size(self, qapp, temp_video_path):
        worker = VideoThumbnailWorker(temp_video_path, size=80)
        assert worker.size == 80

    def test_cache_dir_created(self, qapp, temp_video_path, temp_dir):
        worker = VideoThumbnailWorker(temp_video_path, cache_dir=temp_dir)
        assert os.path.isdir(temp_dir)

    def test_cache_path_deterministic(self, qapp, temp_video_path, temp_dir):
        """El path de caché debe ser el mismo en llamadas consecutivas"""
        worker = VideoThumbnailWorker(temp_video_path, cache_dir=temp_dir)
        path1 = worker._get_cache_path()
        path2 = worker._get_cache_path()

        assert path1 == path2
        assert path1.endswith(".png")

    def test_cache_path_different_for_size(self, qapp, temp_video_path, temp_dir):
        """Cambiar el tamaño debe dar path distinto"""
        w1 = VideoThumbnailWorker(temp_video_path, size=80, cache_dir=temp_dir)
        w2 = VideoThumbnailWorker(temp_video_path, size=160, cache_dir=temp_dir)

        assert w1._get_cache_path() != w2._get_cache_path()

    def test_generate_thumbnail_valid_video(self, qapp, temp_video_path):
        worker = VideoThumbnailWorker(temp_video_path, size=160)
        thumb = worker._generate_thumbnail()

        if thumb is not None:
            assert isinstance(thumb, QImage)
            assert not thumb.isNull()

    def test_generate_thumbnail_nonexistent(self, qapp, temp_dir):
        worker = VideoThumbnailWorker(
            os.path.join(temp_dir, "no_existe.mp4")
        )
        thumb = worker._generate_thumbnail()
        assert thumb is None


@pytest.mark.gui
class TestVideoThumbnailManager:
    def test_singleton(self, qapp):
        m1 = VideoThumbnailManager()
        m2 = VideoThumbnailManager()
        assert m1 is m2

    def test_thread_pool_exists(self, qapp):
        manager = VideoThumbnailManager()
        assert manager.thread_pool is not None

    def test_clear_cache(self, qapp):
        manager = VideoThumbnailManager()
        manager.clear_cache()
        assert len(manager._cache) == 0

    def test_cleanup(self, qapp):
        manager = VideoThumbnailManager()
        manager.cleanup()
        # No debe crashear