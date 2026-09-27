"""Tests para file_manager.py

FIX v2: añadidos tests de video + propiedades
"""
import os
import pytest
import numpy as np
import cv2

from core.file_manager import FileManager
from core.models import (
    CaptureSettings,
    ImageFormat,
    VideoFormat,
    Resolution,
)


class TestFileManagerInit:
    def test_init(self):
        settings = CaptureSettings()
        fm = FileManager(settings)
        assert fm.settings is settings
        # Interpolación leída de config
        assert fm.image_interpolation in ("linear", "nearest", "cubic", "area", "lanczos4")
        assert fm.video_interpolation in ("linear", "nearest", "cubic", "area", "lanczos4")


class TestDirectoryHandling:
    def test_ensure_directory_creates(self, temp_dir):
        fm = FileManager(CaptureSettings())
        new_dir = os.path.join(temp_dir, "subdir", "nested")
        result = fm.ensure_directory(new_dir)
        assert os.path.isdir(result)

    def test_ensure_directory_existing(self, temp_dir):
        fm = FileManager(CaptureSettings())
        result = fm.ensure_directory(temp_dir)
        assert os.path.isdir(result)

    def test_ensure_directory_expands_user(self):
        """`~` debe expandirse"""
        fm = FileManager(CaptureSettings())
        result = fm.ensure_directory("~/test_camcap_dir")
        assert os.path.isdir(result)
        # Cleanup
        try:
            os.rmdir(result)
        except Exception:
            pass


class TestFilenameGeneration:
    def test_generate_filename_has_extension(self):
        fm = FileManager(CaptureSettings())
        filename = fm.generate_filename("foto_{timestamp}", "Cam1", ".jpg")
        assert filename.endswith(".jpg")

    def test_generate_filename_timestamp_substituted(self):
        fm = FileManager(CaptureSettings())
        filename = fm.generate_filename("foto_{timestamp}", "Cam1", ".jpg")
        assert "{timestamp}" not in filename
        assert "foto_" in filename

    def test_generate_filename_camera_name(self):
        fm = FileManager(CaptureSettings())
        filename = fm.generate_filename(
            "foto_{camera_name}_{timestamp}", "Cam1", ".jpg"
        )
        assert "Cam1" in filename
        assert filename.endswith(".jpg")

    def test_generate_filename_invalid_chars_removed(self):
        fm = FileManager(CaptureSettings())
        filename = fm.generate_filename("foto:test<>file", "Cam", ".jpg")
        for char in '<>:"/\\|?*':
            assert char not in filename


class TestSaveImage:
    def test_save_jpg(self, temp_dir, sample_bgr_image):
        settings = CaptureSettings(image_format=ImageFormat.JPG)
        fm = FileManager(settings)

        path, size = fm.save_image(
            sample_bgr_image, temp_dir, "test_image",
            ImageFormat.JPG, 85, Resolution.VGA
        )

        assert os.path.exists(path)
        assert size > 0
        assert path.endswith(".jpg")

    def test_save_png(self, temp_dir, sample_bgr_image):
        settings = CaptureSettings(image_format=ImageFormat.PNG)
        fm = FileManager(settings)

        path, size = fm.save_image(
            sample_bgr_image, temp_dir, "test_image",
            ImageFormat.PNG, 85, Resolution.VGA
        )

        assert os.path.exists(path)
        assert path.endswith(".png")

    def test_save_bmp(self, temp_dir, sample_bgr_image):
        fm = FileManager(CaptureSettings())
        path, size = fm.save_image(
            sample_bgr_image, temp_dir, "test_bmp",
            ImageFormat.BMP, 85, Resolution.VGA
        )
        assert os.path.exists(path)
        assert path.endswith(".bmp")

    def test_save_resizes_oversized_image(self, temp_dir):
        """Imagen grande debe redimensionarse a la resolución pedida"""
        fm = FileManager(CaptureSettings())
        img = np.zeros((1080, 1920, 3), dtype=np.uint8)

        path, size = fm.save_image(
            img, temp_dir, "resized", ImageFormat.JPG, 85, Resolution.VGA
        )

        saved = cv2.imread(path)
        assert saved.shape[0] == 480
        assert saved.shape[1] == 640

    def test_save_no_resize_same_size(self, temp_dir, sample_bgr_image):
        """Si ya tiene el tamaño, no redimensiona"""
        fm = FileManager(CaptureSettings())
        # sample_bgr_image es 480x640 = VGA
        path, size = fm.save_image(
            sample_bgr_image, temp_dir, "same_size",
            ImageFormat.JPG, 85, Resolution.VGA
        )

        saved = cv2.imread(path)
        assert saved.shape[:2] == (480, 640)

    def test_save_unicode_path(self, temp_dir, sample_bgr_image):
        """Soporte de tildes/ñ en rutas"""
        unicode_dir = os.path.join(temp_dir, "fotos_ñandú")
        os.makedirs(unicode_dir, exist_ok=True)

        fm = FileManager(CaptureSettings())
        path, size = fm.save_image(
            sample_bgr_image, unicode_dir, "foto_año",
            ImageFormat.JPG, 85, Resolution.VGA
        )

        assert os.path.exists(path)

    def test_save_quality_affects_size(self, temp_dir, sample_bgr_image):
        """JPG con menor calidad debe pesar menos"""
        fm = FileManager(CaptureSettings())

        path_low, size_low = fm.save_image(
            sample_bgr_image, temp_dir, "low",
            ImageFormat.JPG, 10, Resolution.VGA
        )
        path_high, size_high = fm.save_image(
            sample_bgr_image, temp_dir, "high",
            ImageFormat.JPG, 95, Resolution.VGA
        )

        assert size_low < size_high, \
            f"Calidad 10 ({size_low}) >= calidad 95 ({size_high})"


class TestSaveVideoFromFrames:
    def test_save_video_avi(self, temp_dir):
        """Guardar video desde frames debe crear archivo"""
        fm = FileManager(CaptureSettings(video_format=VideoFormat.AVI))

        frames = []
        for i in range(30):
            frame = np.zeros((240, 320, 3), dtype=np.uint8)
            frame[:] = (i * 8, 100, 200 - i * 6)
            frames.append(frame)

        output_path = os.path.join(temp_dir, "test_video.avi")
        path, size = fm.save_video_from_frames(
            frames, output_path, "MJPG", 30, Resolution.QVGA
        )

        assert os.path.exists(path)
        assert size > 0

    def test_save_video_empty_frames_raises(self, temp_dir):
        """Lista vacía debe lanzar excepción"""
        fm = FileManager(CaptureSettings())
        output_path = os.path.join(temp_dir, "empty.avi")

        with pytest.raises(Exception):
            fm.save_video_from_frames(
                [], output_path, "MJPG", 30, Resolution.QVGA
            )

    def test_save_video_resizes_frames(self, temp_dir):
        """Frames de tamaño distinto deben redimensionarse"""
        fm = FileManager(CaptureSettings(video_format=VideoFormat.AVI))

        # Frames más grandes que la resolución objetivo
        frames = [np.zeros((480, 640, 3), dtype=np.uint8) for _ in range(10)]

        output_path = os.path.join(temp_dir, "resized.avi")
        path, size = fm.save_video_from_frames(
            frames, output_path, "MJPG", 15, Resolution.QVGA
        )

        assert os.path.exists(path)
        # Verificar que el video tiene la resolución correcta
        cap = cv2.VideoCapture(path)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        assert (w, h) == (320, 240)


class TestGetCaptureInfo:
    def test_info_image(self, temp_image_path):
        fm = FileManager(CaptureSettings())
        info = fm.get_capture_info(temp_image_path)

        assert info["type"] == "image"
        assert info["width"] == 640
        assert info["height"] == 480
        assert info["format"] == "JPG"
        assert info["size"] > 0

    def test_info_video(self, temp_video_path):
        fm = FileManager(CaptureSettings())
        info = fm.get_capture_info(temp_video_path)

        assert info["type"] == "video"
        assert info["width"] > 0
        assert info["height"] > 0
        assert info["frames"] > 0

    def test_info_nonexistent(self):
        fm = FileManager(CaptureSettings())
        info = fm.get_capture_info("/ruta/que/no/existe.jpg")
        assert info == {}

    def test_info_has_filename(self, temp_image_path):
        fm = FileManager(CaptureSettings())
        info = fm.get_capture_info(temp_image_path)
        assert "filename" in info
        assert info["filename"] == "test_image.jpg"


class TestReloadConfig:
    def test_reload_updates_interpolation(self):
        fm = FileManager(CaptureSettings())
        result = fm.reload_config()
        assert result is True
        # Después de reload, sigue siendo válido
        assert fm.image_interpolation in ("linear", "nearest", "cubic", "area", "lanczos4")