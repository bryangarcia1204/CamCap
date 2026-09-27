"""Tests para models.py

FIX v2:
- No depende de "dshow" (Linux/Mac usan v4l2/avfoundation)
- Tests de propiedades en lugar de valores exactos
"""
import pytest
import numpy as np
from datetime import datetime

from core.models import (
    CameraDevice, CameraStatus,
    ImageFormat, VideoFormat, Resolution, QualityProfile,
    CaptureSettings, CaptureItem, LocalCameraInfo,
)


class TestCameraStatus:
    def test_all_statuses_exist(self):
        statuses = [
            CameraStatus.DISCONNECTED,
            CameraStatus.CONNECTING,
            CameraStatus.CONNECTED,
            CameraStatus.ERROR,
            CameraStatus.RECORDING,
        ]
        assert len(statuses) == 5

    def test_status_values_are_strings(self):
        for status in CameraStatus:
            assert isinstance(status.value, str)
            assert len(status.value) > 0


class TestImageFormat:
    def test_extensions_include_common(self):
        exts = ImageFormat.get_extensions()
        for common in ("jpg", "png", "bmp"):
            assert common in exts

    def test_default(self):
        assert ImageFormat.get_default() == ImageFormat.JPG

    def test_all_have_value(self):
        for fmt in ImageFormat:
            assert fmt.value
            assert fmt.value.islower()


class TestVideoFormat:
    def test_extensions_include_common(self):
        exts = VideoFormat.get_extensions()
        for common in ("mp4", "avi", "mkv"):
            assert common in exts

    def test_default(self):
        assert VideoFormat.get_default() == VideoFormat.AVI


class TestResolution:
    def test_vga_dimensions(self):
        assert Resolution.VGA.width == 640
        assert Resolution.VGA.height == 480

    def test_full_hd_dimensions(self):
        assert Resolution.FULL_HD.width == 1920
        assert Resolution.FULL_HD.height == 1080

    def test_get_size_returns_tuple(self):
        size = Resolution.HD.get_size()
        assert isinstance(size, tuple)
        assert len(size) == 2
        assert size == (1280, 720)

    def test_display_names_contain_dimensions(self):
        options = Resolution.get_options()
        assert any("640x480" in opt for opt in options)
        assert any("1920x1080" in opt for opt in options)

    def test_all_resolutions_have_positive_dimensions(self):
        for res in Resolution:
            assert res.width > 0
            assert res.height > 0


class TestQualityProfile:
    def test_all_have_quality(self):
        for profile in QualityProfile:
            assert 1 <= profile.quality_value <= 100

    def test_default(self):
        profile = QualityProfile.get_default()
        assert isinstance(profile, QualityProfile)


class TestCameraDeviceIP:
    def test_video_url_format(self):
        cam = CameraDevice(id=0, name="Test", ip="192.168.1.1", port=4747)
        assert cam.video_url == "http://192.168.1.1:4747/video"

    def test_video_url_shot_type(self):
        cam = CameraDevice(
            id=0, name="Test", ip="192.168.1.1", port=4747,
            url_type="shot"
        )
        assert cam.video_url == "http://192.168.1.1:4747/shot.jpg"

    def test_camera_type_is_ip(self):
        cam = CameraDevice(id=0, name="Test", ip="1.1.1.1", port=80)
        assert cam.camera_type == "ip"


class TestCameraDeviceScreen:
    def test_video_url_screen(self):
        cam = CameraDevice(
            id=0, name="Screen", ip="SCREEN",
            port=0, is_screen=True
        )
        assert cam.video_url == "screen://"

    def test_camera_type_is_screen(self):
        cam = CameraDevice(
            id=0, name="S", ip="SCREEN", port=0, is_screen=True
        )
        assert cam.camera_type == "screen"

    def test_display_name_has_emoji(self):
        cam = CameraDevice(
            id=0, name="Pantalla 1", ip="SCREEN",
            port=0, is_screen=True
        )
        assert "🖥️" in cam.display_name


class TestCameraDeviceLocal:
    def test_video_url_local(self):
        cam = CameraDevice(
            id=0, name="Local", ip="LOCAL",
            port=0, is_local=True, camera_index=2
        )
        assert cam.video_url == "local://2"

    def test_camera_type_is_local(self):
        cam = CameraDevice(
            id=0, name="L", ip="LOCAL",
            port=0, is_local=True, camera_index=0
        )
        assert cam.camera_type == "local"

    def test_display_name_has_local_emoji(self):
        cam = CameraDevice(
            id=0, name="Cam 0", ip="LOCAL",
            port=0, is_local=True, camera_index=0
        )
        assert "📹" in cam.display_name


class TestCameraDeviceDisplayName:
    def test_ip_display_name_includes_ip_and_port(self):
        cam = CameraDevice(id=0, name="Mi Cam", ip="1.1.1.1", port=8080)
        assert "Mi Cam" in cam.display_name
        assert "1.1.1.1" in cam.display_name
        assert "8080" in cam.display_name


class TestCameraDeviceDefaults:
    def test_status_default_disconnected(self):
        cam = CameraDevice(id=0, name="Test", ip="1.1.1.1", port=80)
        assert cam.status == CameraStatus.DISCONNECTED

    def test_no_frame_initially(self):
        cam = CameraDevice(id=0, name="Test", ip="1.1.1.1", port=80)
        assert cam.current_frame is None

    def test_url_type_default_video(self):
        cam = CameraDevice(id=0, name="Test", ip="1.1.1.1", port=80)
        assert cam.url_type == "video"


class TestCaptureSettings:
    def test_defaults(self):
        s = CaptureSettings()
        assert s.image_format == ImageFormat.JPG
        assert s.video_format == VideoFormat.MP4
        assert 1 <= s.image_quality <= 100
        assert 1 <= s.video_quality <= 100
        assert s.video_fps > 0

    def test_get_image_size(self):
        s = CaptureSettings(image_resolution=Resolution.HD)
        assert s.get_image_size() == (1280, 720)

    def test_get_video_size(self):
        s = CaptureSettings(video_resolution=Resolution.FULL_HD)
        assert s.get_video_size() == (1920, 1080)

    def test_get_image_extension(self):
        s = CaptureSettings(image_format=ImageFormat.PNG)
        assert s.get_image_extension() == ".png"

    def test_get_video_extension(self):
        s = CaptureSettings(video_format=VideoFormat.MKV)
        assert s.get_video_extension() == ".mkv"


class TestCaptureItem:
    def test_filename_property(self):
        item = CaptureItem(
            path="/home/user/foto.jpg",
            timestamp=datetime.now(),
            camera_name="Cam1",
            item_type="image",
            format="JPG",
            size=1024,
            resolution="640x480",
            quality=85,
        )
        assert item.filename == "foto.jpg"

    def test_size_mb_property(self):
        item = CaptureItem(
            path="/x.jpg",
            timestamp=datetime.now(),
            camera_name="C",
            item_type="image",
            format="JPG",
            size=2 * 1024 * 1024,
            resolution="VGA",
            quality=85,
        )
        assert 1.9 <= item.size_mb <= 2.1


class TestLocalCameraInfo:
    def test_creation_defaults(self):
        info = LocalCameraInfo(index=0, name="Cam 0")
        assert info.index == 0
        assert info.available is True
        # No verificar backend específico (dshow/v4l2/avfoundation)
        assert isinstance(info.backend, str)
        assert len(info.backend) > 0

    def test_backend_any_platform(self):
        """El backend depende del SO; solo verificamos que es string válido"""
        info = LocalCameraInfo(index=0, name="Cam 0")
        valid_backends = ("dshow", "v4l2", "avfoundation", "msmf", "gstreamer")
        assert info.backend in valid_backends, \
            f"Backend '{info.backend}' no reconocido"

    def test_custom_backend(self):
        info = LocalCameraInfo(index=0, name="Test", backend="custom")
        assert info.backend == "custom"

    def test_unavailable_camera(self):
        info = LocalCameraInfo(index=5, name="No Existe", available=False)
        assert info.available is False