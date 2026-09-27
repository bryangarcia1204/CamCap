"""Tests para local_camera_engine.py

FIX v2: rangos + config-driven
"""
import pytest
import numpy as np
from unittest.mock import MagicMock, patch

from core.engine.local_camera_engine import LocalCameraThread, LocalCameraDetector
from utils.config_loader import advanced_config


class TestLocalCameraThreadInit:
    def test_init(self, camera_local):
        thread = LocalCameraThread(camera_local)
        assert thread.camera is camera_local
        assert thread._running is False
        assert thread._av_recorder is None

    def test_fps_from_config(self, camera_local):
        thread = LocalCameraThread(camera_local)
        cfg = advanced_config.get_all()
        assert thread.fps == cfg.get("target_fps", 30)

    def test_has_adaptive_throttle(self, camera_local):
        thread = LocalCameraThread(camera_local)
        cfg = advanced_config.get_all()

        assert thread._adaptive_throttle is not None
        assert thread._adaptive_throttle.target_cpu == cfg.get(
            "throttle_target_cpu", 1.5
        )


class TestLocalCameraThreadMethods:
    def test_capture_frame_none(self, camera_local):
        thread = LocalCameraThread(camera_local)
        assert thread.capture_frame() is None

    def test_capture_frame_with_frame(self, camera_local):
        thread = LocalCameraThread(camera_local)
        thread.camera.current_frame = np.zeros((480, 640, 3), dtype=np.uint8)

        frame = thread.capture_frame()
        assert frame is not None
        assert frame.shape == (480, 640, 3)

    def test_stop_recording_no_op(self, camera_local):
        thread = LocalCameraThread(camera_local)
        assert thread.stop_recording() is None

    def test_is_recording_false(self, camera_local):
        thread = LocalCameraThread(camera_local)
        assert thread.is_recording() is False


class TestLocalCameraDetector:
    @patch("cv2.VideoCapture")
    def test_detect_no_cameras(self, mock_cap):
        """Si no hay cámaras, devuelve lista vacía"""
        mock_instance = MagicMock()
        mock_instance.isOpened.return_value = False
        mock_cap.return_value = mock_instance

        result = LocalCameraDetector.detect_available_cameras(max_devices=2)
        assert result == []

    @patch("cv2.VideoCapture")
    def test_detect_returns_list(self, mock_cap):
        """Debe devolver siempre una lista"""
        mock_instance = MagicMock()
        mock_instance.isOpened.return_value = False
        mock_cap.return_value = mock_instance

        result = LocalCameraDetector.detect_available_cameras(max_devices=1)
        assert isinstance(result, list)