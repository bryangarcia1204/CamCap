"""Tests para screen_camera_engine.py

FIX v2: config-driven
"""
import pytest
import numpy as np

from core.engine.screen_camera_engine import ScreenCameraThread, ScreenCameraManager
from utils.config_loader import advanced_config


class TestScreenCameraThreadInit:
    def test_init(self, camera_screen):
        thread = ScreenCameraThread(camera_screen)
        assert thread.camera is camera_screen
        assert thread._running is False
        assert thread._av_recorder is None

    def test_has_adaptive_throttle(self, camera_screen):
        """El throttle debe estar inicializado desde config"""
        thread = ScreenCameraThread(camera_screen)
        cfg = advanced_config.get_all()

        assert thread._adaptive_throttle is not None
        # Valor viene de config
        assert thread._adaptive_throttle.target_cpu == cfg.get(
            "throttle_target_cpu", 1.5
        )

    def test_fps_from_config(self, camera_screen):
        """El FPS se lee de advanced_config"""
        thread = ScreenCameraThread(camera_screen)
        cfg = advanced_config.get_all()

        expected_fps = cfg.get("target_fps", 30)
        assert thread.fps == expected_fps

    def test_display_size_defaults(self, camera_screen):
        """Los defaults de display deben estar en rangos razonables"""
        thread = ScreenCameraThread(camera_screen)

        assert 320 <= thread._display_width <= 1920
        assert 240 <= thread._display_height <= 1080


class TestScreenCameraThreadMethods:
    def test_capture_frame_no_frame(self, camera_screen):
        thread = ScreenCameraThread(camera_screen)
        assert thread.capture_frame() is None

    def test_capture_frame_with_frame(self, camera_screen):
        thread = ScreenCameraThread(camera_screen)
        thread.camera.current_frame = np.zeros((480, 640, 3), dtype=np.uint8)

        frame = thread.capture_frame()
        assert frame is not None
        assert frame.shape == (480, 640, 3)

    def test_stop_recording_no_op(self, camera_screen):
        thread = ScreenCameraThread(camera_screen)
        assert thread.stop_recording() is None

    def test_is_recording_false(self, camera_screen):
        thread = ScreenCameraThread(camera_screen)
        assert thread.is_recording() is False

    def test_is_audio_active_no_stream(self, camera_screen):
        from audio.audio_manager import audio_manager
        audio_manager.stop_camera_audio(camera_screen.id)

        thread = ScreenCameraThread(camera_screen)
        assert thread._is_audio_active() is False


class TestScreenCameraManager:
    def test_init(self):
        manager = ScreenCameraManager()
        assert manager.camera is None
        assert manager.thread is None

    def test_get_camera_none(self):
        manager = ScreenCameraManager()
        assert manager.get_camera() is None

    def test_get_thread_none(self):
        manager = ScreenCameraManager()
        assert manager.get_thread() is None


class TestScreenCameraCapture:
    """Tests que requieren QApplication"""

    @pytest.mark.gui
    def test_qimage_to_numpy_valid(self, qapp):
        """La conversión QImage→numpy debe funcionar"""
        from PySide6.QtGui import QImage
        from core.engine.screen_camera_engine import ScreenCameraThread
        from core.models import CameraDevice

        cam = CameraDevice(
            id=0, name="Screen", ip="SCREEN",
            port=0, is_screen=True
        )
        thread = ScreenCameraThread(cam)

        # Crear QImage de prueba
        qimage = QImage(640, 480, QImage.Format_RGB888)
        qimage.fill(0x00FF00)  # Verde

        result = thread._qimage_to_numpy_safe(qimage)

        assert result is not None
        assert result.shape == (480, 640, 3)
        assert result.dtype == np.uint8

    @pytest.mark.gui
    def test_qimage_to_numpy_null(self, qapp):
        """QImage nulo debe devolver None"""
        from PySide6.QtGui import QImage
        from core.engine.screen_camera_engine import ScreenCameraThread
        from core.models import CameraDevice

        cam = CameraDevice(
            id=0, name="Screen", ip="SCREEN",
            port=0, is_screen=True
        )
        thread = ScreenCameraThread(cam)

        qimage = QImage()  # Nulo
        result = thread._qimage_to_numpy_safe(qimage)

        assert result is None