"""
Tests para settings_manager.py

FIX v2:
- Uso de rangos y propiedades
- Cache hit/miss verificables
- No depende de estado global
"""
import os
import pytest
from PySide6.QtCore import QSettings

from core.settings_manager import SettingsManager
from core.models import (
    CameraDevice, CaptureSettings, ImageFormat,
    VideoFormat, Resolution,
)


@pytest.fixture(scope="function")
def fresh_manager(temp_dir):
    """Crea SettingsManager aislado con archivo .ini temporal"""
    settings_file = os.path.join(temp_dir, "test_settings.ini")

    SettingsManager._instance = None
    manager = SettingsManager()
    manager._settings = QSettings(settings_file, QSettings.IniFormat)
    manager._settings.clear()
    manager._settings.sync()
    manager._invalidate_all_caches()

    yield manager

    try:
        manager._settings.clear()
        manager._settings.sync()
    except Exception:
        pass
    SettingsManager._instance = None


class TestCameras:
    def test_get_cameras_empty(self, fresh_manager):
        cameras = fresh_manager.get_cameras()
        assert cameras == []

    def test_save_and_get_camera(self, fresh_manager, camera_ip):
        result = fresh_manager.save_camera(camera_ip)
        assert result is True

        cameras = fresh_manager.get_cameras()
        assert len(cameras) == 1
        assert cameras[0].name == camera_ip.name

    def test_save_camera_returns_camera_with_valid_id(self, fresh_manager, camera_ip):
        """Tras save_camera, la cámara debe tener un ID válido"""
        fresh_manager.save_camera(camera_ip)
        cameras = fresh_manager.get_cameras()

        assert len(cameras) > 0
        # El ID debe ser >= 0
        assert cameras[0].id >= 0

    def test_save_duplicate_camera_replaces(self, fresh_manager, camera_ip):
        """Guardar la misma cámara 2 veces no debe duplicarla"""
        fresh_manager.save_camera(camera_ip)
        fresh_manager.save_camera(camera_ip)

        cameras = fresh_manager.get_cameras()
        assert len(cameras) == 1

    def test_remove_camera(self, fresh_manager, camera_ip):
        fresh_manager.save_camera(camera_ip)
        cameras = fresh_manager.get_cameras()
        assert len(cameras) == 1

        cam_id = cameras[0].id
        result = fresh_manager.remove_camera(cam_id)
        assert result is True

        cameras = fresh_manager.get_cameras()
        assert len(cameras) == 0

    def test_remove_nonexistent_camera(self, fresh_manager):
        """Eliminar cámara inexistente no debe fallar"""
        result = fresh_manager.remove_camera(9999)
        # Puede ser True o False, lo importante es que no crashee
        assert isinstance(result, bool)


class TestCacheInvalidation:
    def test_cache_invalidation_on_save(self, fresh_manager, camera_ip):
        """Guardar debe invalidar la caché"""
        cameras1 = fresh_manager.get_cameras()
        assert len(cameras1) == 0

        # Ahora hay caché
        assert fresh_manager._cameras_cache is not None

        # Guardar debe invalidar
        fresh_manager.save_camera(camera_ip)
        assert fresh_manager._cameras_cache is None

    def test_cache_invalidation_on_remove(self, fresh_manager, camera_ip):
        fresh_manager.save_camera(camera_ip)
        fresh_manager.get_cameras()

        # Ahora hay caché
        assert fresh_manager._cameras_cache is not None

        cameras = fresh_manager.get_cameras()
        fresh_manager.remove_camera(cameras[0].id)

        assert fresh_manager._cameras_cache is None

    def test_cache_hit_returns_same_data(self, fresh_manager, camera_ip):
        """Dos lecturas consecutivas sin cambios deben devolver lo mismo"""
        fresh_manager.save_camera(camera_ip)

        cameras1 = fresh_manager.get_cameras()
        cameras2 = fresh_manager.get_cameras()

        assert len(cameras1) == len(cameras2)
        assert cameras1[0].name == cameras2[0].name


class TestCaptureSettings:
    def test_get_default(self, fresh_manager):
        settings = fresh_manager.get_capture_settings()
        assert isinstance(settings, CaptureSettings)
        assert settings.image_format == ImageFormat.JPG
        assert settings.video_format == VideoFormat.AVI

    def test_save_and_get(self, fresh_manager):
        settings = CaptureSettings(
            default_name="test_{timestamp}",
            image_quality=95,
            video_fps=25,
        )
        fresh_manager.save_capture_settings(settings)

        loaded = fresh_manager.get_capture_settings()
        assert loaded.default_name == "test_{timestamp}"
        assert loaded.image_quality == 95
        assert loaded.video_fps == 25

    def test_save_invalidates_cache(self, fresh_manager):
        fresh_manager.get_capture_settings()  # poblar caché
        assert fresh_manager._capture_settings_cache is not None

        settings = CaptureSettings(image_quality=50)
        fresh_manager.save_capture_settings(settings)

        assert fresh_manager._capture_settings_cache is None


class TestDetectionSettings:
    def test_get_default(self, fresh_manager):
        settings = fresh_manager.get_detection_settings()
        assert "motion_enabled" in settings
        assert "face_enabled" in settings

    def test_save_and_get(self, fresh_manager):
        fresh_manager.save_detection_settings({
            "motion_enabled": True,
            "motion_sensitivity": 50,
        })

        loaded = fresh_manager.get_detection_settings()
        assert loaded["motion_enabled"] is True
        assert loaded["motion_sensitivity"] == 50


class TestAdvancedSettings:
    def test_get_advanced_has_defaults(self, fresh_manager):
        settings = fresh_manager.get_advanced_settings()
        # Debe tener ~90 parámetros
        assert len(settings) >= 80, \
            f"Solo se cargaron {len(settings)} parámetros avanzados"

    def test_get_advanced_values_reasonable(self, fresh_manager):
        """Los valores deben estar en rangos válidos"""
        settings = fresh_manager.get_advanced_settings()

        assert 1 <= settings["target_fps"] <= 120
        assert 0.1 <= settings["throttle_target_cpu"] <= 8
        assert 0.1 <= settings["throttle_target_gpu"] <= 1.0


class TestUI:
    def test_get_ui_defaults(self, fresh_manager):
        ui = fresh_manager.get_ui_settings()
        assert "theme" in ui
        assert "camera_grid_columns" in ui

    def test_save_and_get(self, fresh_manager):
        fresh_manager.save_ui_settings({
            "theme": "light",
            "camera_grid_columns": 3,
        })

        loaded = fresh_manager.get_ui_settings()
        assert loaded["theme"] == "light"
        assert loaded["camera_grid_columns"] == 3


class TestClearAll:
    def test_clear_all_removes_cameras(self, fresh_manager, camera_ip):
        fresh_manager.save_camera(camera_ip)
        fresh_manager.clear_all()

        cameras = fresh_manager.get_cameras()
        assert len(cameras) == 0