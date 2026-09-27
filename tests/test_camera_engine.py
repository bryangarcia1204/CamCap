"""Tests para camera_engine.py

FIX v2: config-driven + rangos
"""
import pytest
import numpy as np

from core.engine.camera_engine import CameraThread, CameraManager
from core.models import CameraStatus
from utils.config_loader import advanced_config


class TestCameraThreadInit:
    def test_init_default(self, camera_ip):
        """El FPS y buffer deben coincidir con advanced_config"""
        thread = CameraThread(camera_ip)
        cfg = advanced_config.get_all()

        assert thread.camera is camera_ip
        assert thread.fps == cfg.get("target_fps", 30), \
            f"fps={thread.fps} != cfg.target_fps={cfg.get('target_fps')}"
        assert thread._buffer_size == cfg.get("buffer_size", 1)
        assert thread._running is False
        assert thread._frames_processed == 0
        assert thread._av_recorder is None

    def test_has_adaptive_throttle(self, camera_ip):
        """El throttle debe estar inicializado con valores de config"""
        thread = CameraThread(camera_ip)
        cfg = advanced_config.get_all()

        assert thread._adaptive_throttle is not None
        # Valores vienen de config, no hardcodeados
        assert thread._adaptive_throttle.target_cpu == cfg.get("throttle_target_cpu", 1.5)

    def test_has_thread_pool(self, camera_ip):
        thread = CameraThread(camera_ip)
        assert thread._executor is not None

    def test_timeouts_from_config(self, camera_ip):
        """Los timeouts deben coincidir con config"""
        thread = CameraThread(camera_ip)
        cfg = advanced_config.get_all()

        assert thread._connection_timeout == cfg.get("connection_timeout", 2.0)
        assert thread._read_timeout == cfg.get("read_timeout", 2.0)
        assert thread._frame_timeout == cfg.get("frame_timeout", 5.0)


class TestCameraThreadMethods:
    def test_capture_frame_no_frame(self, camera_ip):
        thread = CameraThread(camera_ip)
        assert thread.capture_frame() is None

    def test_capture_frame_with_frame(self, camera_ip):
        thread = CameraThread(camera_ip)
        thread.camera.current_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame = thread.capture_frame()

        assert frame is not None
        assert frame.shape == (480, 640, 3)
        assert frame.dtype == np.uint8

    def test_is_recording_false(self, camera_ip):
        thread = CameraThread(camera_ip)
        assert thread.is_recording() is False

    def test_stop_recording_no_op(self, camera_ip):
        thread = CameraThread(camera_ip)
        assert thread.stop_recording() is None

    def test_is_audio_active_no_stream(self, camera_ip):
        """Sin stream de audio activo, debe retornar False"""
        from plugins.audio.audio_manager import audio_manager
        audio_manager.stop_camera_audio(camera_ip.id)

        thread = CameraThread(camera_ip)
        assert thread._is_audio_active() is False


class TestCameraManager:
    def test_init(self):
        manager = CameraManager()
        assert manager.cameras == {}
        assert manager.threads == {}

    def test_get_camera_nonexistent(self):
        manager = CameraManager()
        assert manager.get_camera(999) is None

    def test_get_active_cameras_empty(self):
        manager = CameraManager()
        assert manager.get_active_cameras() == []

    def test_is_camera_closing(self):
        manager = CameraManager()
        assert manager.is_camera_closing(999) is False