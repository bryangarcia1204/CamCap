"""
Gestor de configuración usando QSettings - CON CACHE
- Cache de get_cameras() con invalidación selectiva
- Cache de settings individuales
- 92 parámetros avanzados ajustables
"""
from PySide6.QtCore import QSettings
from typing import List, Optional, Dict, Any
from core.models import (CameraDevice, CaptureSettings, ImageFormat, VideoFormat,
                    CameraStatus, Resolution)
from utils.logger import get_logger

logger = get_logger("SettingsManager")


class SettingsManager:
    """Singleton para gestionar la configuración - CON CACHE"""

    _instance = None
    _settings = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        self._settings = QSettings("ProCamera", "CameraControl")
        self._settings.setDefaultFormat(QSettings.IniFormat)

        # Caches
        self._cameras_cache: Optional[List[CameraDevice]] = None
        self._capture_settings_cache: Optional[CaptureSettings] = None
        self._detection_settings_cache: Optional[dict] = None
        self._scan_settings_cache: Optional[dict] = None
        self._notification_settings_cache: Optional[dict] = None
        self._advanced_settings_cache: Optional[dict] = None
        self._ui_settings_cache: Optional[dict] = None

        logger.info("⚙️ SettingsManager inicializado (con cache)")

    # ==================== CÁMARAS ====================

    def get_cameras(self) -> List[CameraDevice]:
        """Recupera lista de cámaras (con cache)"""
        logger.debug(f"📷 [get_cameras] cache_hit={self._cameras_cache is not None}")
        if self._cameras_cache is not None:
            return list(self._cameras_cache)

        cameras = []
        count = self._settings.value("cameras/count", 0, type=int)

        seen_ids = set()
        seen_keys = set()

        for i in range(count):
            name = self._settings.value(f"cameras/camera_{i}/name", f"Cámara {i+1}", type=str)
            ip = self._settings.value(f"cameras/camera_{i}/ip", "", type=str)
            port = self._settings.value(f"cameras/camera_{i}/port", 4747, type=int)
            url_type = self._settings.value(f"cameras/camera_{i}/url_type", "video", type=str)
            is_screen = self._settings.value(f"cameras/camera_{i}/is_screen", False, type=bool)
            is_local = self._settings.value(f"cameras/camera_{i}/is_local", False, type=bool)
            camera_index = self._settings.value(f"cameras/camera_{i}/camera_index", 0, type=int)
            auto_flash = self._settings.value(f"cameras/camera_{i}/auto_flash", False, type=bool)

            if is_screen:
                camera_key = "SCREEN"
            elif is_local:
                camera_key = f"LOCAL:{camera_index}"
            else:
                camera_key = f"{ip}:{port}"

            if camera_key in seen_keys:
                logger.warning(f"⚠️ Cámara duplicada ignorada: {name} ({camera_key})")
                continue

            if is_screen or is_local or (ip and ip != ""):
                new_id = i
                while new_id in seen_ids:
                    new_id += 1000

                camera = CameraDevice(
                    id=new_id,
                    name=name,
                    ip="SCREEN" if is_screen else ("LOCAL" if is_local else ip),
                    port=0 if (is_screen or is_local) else port,
                    url_type=url_type,
                    is_screen=is_screen,
                    is_local=is_local,
                    camera_index=camera_index,
                    auto_flash=auto_flash
                )
                cameras.append(camera)
                seen_ids.add(new_id)
                seen_keys.add(camera_key)

        logger.debug(f"📷 [get_cameras] Cargadas {len(cameras)} cámaras de QSettings")
        self._cameras_cache = cameras
        logger.info(f"📷 Cargadas {len(cameras)} cámara(s) (cache miss)")
        return list(cameras)

    def save_camera(self, camera: CameraDevice) -> bool:
        """Guarda una cámara - INVALIDA CACHE"""
        logger.debug(f"📷 [save_cam] id={camera.id}, name={camera.name}, "
             f"is_screen={camera.is_screen}, is_local={camera.is_local}, "
             f"ip={camera.ip}:{camera.port}")
        try:
            cameras = self.get_cameras()

            if camera.is_screen:
                cameras = [c for c in cameras if not c.is_screen]

            existing = next((c for c in cameras if c.id == camera.id), None)
            if existing:
                idx = cameras.index(existing)
                cameras[idx] = camera
            else:
                if camera.id == -1:
                    existing_ids = [c.id for c in cameras]
                    camera.id = max(existing_ids + [-1]) + 1
                cameras.append(camera)

            self._settings.setValue("cameras/count", len(cameras))
            for i, cam in enumerate(cameras):
                self._settings.setValue(f"cameras/camera_{i}/name", cam.name)
                self._settings.setValue(f"cameras/camera_{i}/ip", cam.ip)
                self._settings.setValue(f"cameras/camera_{i}/port", cam.port)
                self._settings.setValue(f"cameras/camera_{i}/url_type", cam.url_type)
                self._settings.setValue(f"cameras/camera_{i}/is_screen", cam.is_screen)
                self._settings.setValue(f"cameras/camera_{i}/is_local", cam.is_local)
                self._settings.setValue(f"cameras/camera_{i}/camera_index", cam.camera_index)
                self._settings.setValue(f"cameras/camera_{i}/auto_flash", cam.auto_flash)

            self._settings.sync()
            self._cameras_cache = None

            logger.debug(f"📷 [save_cam] Guardado OK, total cámaras={len(cameras)}")
            logger.info(f"✅ Cámara guardada: {camera.name}")
            return True
        except Exception as e:
            logger.error(f"Error guardando cámara: {e}", exc_info=True)
            return False

    def remove_camera(self, camera_id: int) -> bool:
        """Elimina una cámara - INVALIDA CACHE"""
        logger.debug(f"📷 [remove_cam] Eliminando id={camera_id}")
        try:
            cameras = self.get_cameras()
            cameras = [c for c in cameras if c.id != camera_id]

            self._settings.setValue("cameras/count", len(cameras))
            for i, cam in enumerate(cameras):
                self._settings.setValue(f"cameras/camera_{i}/name", cam.name)
                self._settings.setValue(f"cameras/camera_{i}/ip", cam.ip)
                self._settings.setValue(f"cameras/camera_{i}/port", cam.port)
                self._settings.setValue(f"cameras/camera_{i}/url_type", cam.url_type)
                self._settings.setValue(f"cameras/camera_{i}/is_screen", cam.is_screen)
                self._settings.setValue(f"cameras/camera_{i}/is_local", cam.is_local)
                self._settings.setValue(f"cameras/camera_{i}/camera_index", cam.camera_index)
                self._settings.setValue(f"cameras/camera_{i}/auto_flash", cam.auto_flash)

            self._settings.sync()
            self._cameras_cache = None

            logger.info(f"✅ Cámara eliminada (ID: {camera_id})")
            return True
        except Exception as e:
            logger.error(f"Error eliminando cámara: {e}")
            return False

    # ==================== CAPTURA ====================

    def get_capture_settings(self) -> CaptureSettings:
        logger.debug(f"⚙️ [get_capture] cache_hit={self._capture_settings_cache is not None}")
        if self._capture_settings_cache is not None:
            return self._capture_settings_cache

        settings = CaptureSettings()
        settings.default_name = self._settings.value(
            "capture/default_name", "foto_{timestamp}", type=str
        )
        settings.default_directory = self._settings.value(
            "capture/default_directory", "~/Pictures/Capturas", type=str
        )

        img_res_value = self._settings.value("capture/image_resolution", "VGA (640x480)", type=str)
        settings.image_resolution = self._get_resolution_from_display_name(img_res_value)

        vid_res_value = self._settings.value("capture/video_resolution", "VGA (640x480)", type=str)
        settings.video_resolution = self._get_resolution_from_display_name(vid_res_value)

        image_format = self._settings.value("capture/image_format", "jpg", type=str)
        try:
            settings.image_format = ImageFormat(image_format.lower())
        except ValueError:
            settings.image_format = ImageFormat.JPG

        video_format = self._settings.value("capture/video_format", "avi", type=str)
        try:
            settings.video_format = VideoFormat(video_format.lower())
        except ValueError:
            settings.video_format = VideoFormat.AVI

        settings.image_quality = self._settings.value("capture/image_quality", 85, type=int)
        settings.video_quality = self._settings.value("capture/video_quality", 80, type=int)
        settings.video_fps = self._settings.value("capture/video_fps", 30, type=int)
        settings.video_codec = self._settings.value("capture/video_codec", "MJPG", type=str)

        self._capture_settings_cache = settings
        return settings

    def _get_resolution_from_display_name(self, display_name: str) -> Resolution:
        for res in Resolution:
            if res.display_name == display_name:
                return res
        return Resolution.VGA

        # ==================== PLUGINS ====================

    def get_plugin_config(self, plugin_name: str) -> dict:
        """
        Lee la config de un plugin.

        Las keys se guardan como `plugin/<plugin_name>/<key>`.
        Si no hay schema, se leen con tipo str (puede perder tipos).
        """
        try:
            schema = None
            # Intentar leer schema si está registrado
            try:
                from core.plugin_api import get_plugin_manager
                pm = get_plugin_manager()
                if pm is not None and pm.context.settings is not None:
                    schema = pm.context.settings.get_schema(plugin_name)
            except Exception:
                pass

            result = {}
            prefix = f"plugin/{plugin_name}/"
            for key in self._settings.allKeys():
                if key.startswith(prefix):
                    short_key = key[len(prefix):]
                    # Si tenemos schema, leer con tipo correcto
                    if schema and short_key in schema:
                        spec = schema[short_key]
                        result[short_key] = self._read_value_with_type(
                            key, spec
                        )
                    else:
                        result[short_key] = self._settings.value(key)
            return result
        except Exception as e:
            logger.error(f"Error leyendo config de plugin '{plugin_name}': {e}")
            return {}

    def _read_value_with_type(self, full_key: str, spec: dict):
        """Lee un valor con el tipo especificado en el schema."""
        type_str = spec.get("type", "str").lower()
        default = spec.get("default")
        try:
            if type_str == "int":
                return self._settings.value(full_key, default, type=int)
            elif type_str == "bool":
                return self._settings.value(full_key, default, type=bool)
            elif type_str == "float":
                return self._settings.value(full_key, default, type=float)
            else:
                return self._settings.value(full_key, default, type=str)
        except Exception:
            return default

    def set_plugin_config(self, plugin_name: str, config: dict) -> bool:
        """Guarda la config de un plugin (batch write + un solo sync)."""
        try:
            prefix = f"plugin/{plugin_name}/"
            for key, value in config.items():
                self._settings.setValue(f"{prefix}{key}", value)
            self._settings.sync()
            logger.debug(
                f"⚙️ [settings] Config de '{plugin_name}' guardada "
                f"({len(config)} keys)"
            )
            return True
        except Exception as e:
            logger.error(f"Error guardando config de plugin '{plugin_name}': {e}")
            return False

    # ==================== CAPTURA ====================

    def save_capture_settings(self, settings: CaptureSettings) -> bool:
        """✅ FIX: batch write + un solo sync"""
        import time
        t0 = time.perf_counter()

        try:
            s = self._settings
            s.setValue("capture/default_name", settings.default_name)
            s.setValue("capture/default_directory", settings.default_directory)
            s.setValue("capture/image_resolution", settings.image_resolution.display_name)
            s.setValue("capture/video_resolution", settings.video_resolution.display_name)
            s.setValue("capture/image_format", settings.image_format.value)
            s.setValue("capture/video_format", settings.video_format.value)
            s.setValue("capture/image_quality", settings.image_quality)
            s.setValue("capture/video_quality", settings.video_quality)
            s.setValue("capture/video_fps", settings.video_fps)
            s.setValue("capture/video_codec", settings.video_codec)

            # ✅ UN solo sync al final
            s.sync()
            self._capture_settings_cache = None
            logger.info("✅ Configuración de captura guardada")
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.debug(f"💾 [save_capture] Guardado en {elapsed_ms:.0f}ms")
            return True
        except Exception as e:
            logger.error(f"Error guardando captura: {e}")
            return False

    # ==================== DETECCIÓN ====================

    def save_detection_settings(self, settings: dict) -> bool:
        """✅ FIX: batch write + un solo sync"""
        try:
            s = self._settings
            for key, value in settings.items():
                s.setValue(f"detection/{key}", value)
            s.sync()
            self._detection_settings_cache = None
            return True
        except Exception as e:
            logger.error(f"Error guardando detección: {e}")
            return False

    # ==================== ESCANEO ====================

    def save_scan_settings(self, settings: dict) -> bool:
        """✅ FIX: batch write + un solo sync"""
        try:
            s = self._settings
            for key, value in settings.items():
                s.setValue(f"scan/{key}", value)
            s.sync()
            self._scan_settings_cache = None
            return True
        except Exception as e:
            logger.error(f"Error guardando escaneo: {e}")
            return False

    # ==================== NOTIFICACIONES ====================

    def save_notification_settings(self, settings: dict) -> bool:
        """✅ FIX: batch write + un solo sync"""
        try:
            s = self._settings
            for key, value in settings.items():
                s.setValue(f"notifications/{key}", value)
            s.sync()
            self._notification_settings_cache = None
            return True
        except Exception as e:
            logger.error(f"Error guardando notificaciones: {e}")
            return False

    # ==================== AVANZADO ====================

    def save_advanced_settings(self, settings: dict) -> bool:
        """✅ FIX: batch write + un solo sync (antes: sync por cada setValue)"""
        try:
            s = self._settings
            for key, value in settings.items():
                s.setValue(f"advanced/{key}", value)
            # ✅ UN solo sync para los 92 parámetros
            s.sync()
            self._advanced_settings_cache = None
            logger.info(f"✅ Configuración avanzada guardada ({len(settings)} params)")
            return True
        except Exception as e:
            logger.error(f"Error guardando avanzado: {e}")
            return False

    # ==================== UI ====================

    def save_ui_settings(self, ui_settings: dict) -> bool:
        """✅ FIX: batch write + un solo sync"""
        try:
            s = self._settings
            if "geometry" in ui_settings:
                s.setValue("ui/geometry", ui_settings["geometry"])
            if "theme" in ui_settings:
                s.setValue("ui/theme", ui_settings["theme"])
            if "camera_grid_columns" in ui_settings:
                s.setValue("ui/camera_grid_columns", ui_settings["camera_grid_columns"])

            s.sync()
            self._ui_settings_cache = None
            return True
        except Exception as e:
            logger.error(f"Error guardando UI: {e}")
            return False

    # ==================== DETECCIÓN ====================

    def get_detection_settings(self) -> dict:
        if self._detection_settings_cache is not None:
            return dict(self._detection_settings_cache)

        settings = {
            "motion_enabled": self._settings.value("detection/motion_enabled", False, type=bool),
            "motion_sensitivity": self._settings.value("detection/motion_sensitivity", 25, type=int),
            "motion_min_area": self._settings.value("detection/motion_min_area", 500, type=int),
            "motion_cooldown": self._settings.value("detection/motion_cooldown", 5.0, type=float),
            "face_enabled": self._settings.value("detection/face_enabled", False, type=bool),
            "face_tolerance": self._settings.value("detection/face_tolerance", 0.6, type=float),
            "notify_windows": self._settings.value("detection/notify_windows", True, type=bool),
            "notify_telegram": self._settings.value("detection/notify_telegram", False, type=bool),
            "auto_record_on_motion": self._settings.value("detection/auto_record_on_motion", False, type=bool),
            "auto_record_timeout": self._settings.value("detection/auto_record_timeout", 2, type=int),
            "auto_flash_on_motion": self._settings.value("detection/auto_flash_on_motion", False, type=bool),
            "enhance_on_capture": self._settings.value("detection/enhance_on_capture", True, type=bool),
            "enhance_threshold": self._settings.value("detection/enhance_threshold", 0.6, type=float),
        }
        self._detection_settings_cache = settings
        return dict(settings)

    def save_detection_settings(self, settings: dict) -> bool:
        try:
            for key, value in settings.items():
                self._settings.setValue(f"detection/{key}", value)
            self._settings.sync()
            self._detection_settings_cache = None
            return True
        except Exception as e:
            logger.error(f"Error guardando detección: {e}")
            return False

    # ==================== ESCANEO ====================

    def get_scan_settings(self) -> dict:
        if self._scan_settings_cache is not None:
            return dict(self._scan_settings_cache)

        settings = {
            "enabled": self._settings.value("scan/enabled", False, type=bool),
            "auto_correct": self._settings.value("scan/auto_correct", True, type=bool),
            "enhance_mode": self._settings.value("scan/enhance_mode", "auto", type=str),
            "tesseract_path": self._settings.value("scan/tesseract_path", "", type=str),
            "language": self._settings.value("scan/language", "spa+eng", type=str),
            "save_original": self._settings.value("scan/save_original", False, type=bool),
            "save_corrected": self._settings.value("scan/save_corrected", True, type=bool),
            "save_text": self._settings.value("scan/save_text", False, type=bool),
        }
        self._scan_settings_cache = settings
        return dict(settings)

    def save_scan_settings(self, settings: dict) -> bool:
        try:
            for key, value in settings.items():
                self._settings.setValue(f"scan/{key}", value)
            self._settings.sync()
            self._scan_settings_cache = None
            return True
        except Exception as e:
            logger.error(f"Error guardando escaneo: {e}")
            return False

    # ==================== NOTIFICACIONES ====================

    def get_notification_settings(self) -> dict:
        if self._notification_settings_cache is not None:
            return dict(self._notification_settings_cache)

        settings = {
            "telegram_enabled": self._settings.value("notifications/telegram_enabled", False, type=bool),
            "telegram_token": self._settings.value("notifications/telegram_token", "", type=str),
            "telegram_chat_id": self._settings.value("notifications/telegram_chat_id", "", type=str),
        }
        self._notification_settings_cache = settings
        return dict(settings)

    def save_notification_settings(self, settings: dict) -> bool:
        try:
            for key, value in settings.items():
                self._settings.setValue(f"notifications/{key}", value)
            self._settings.sync()
            self._notification_settings_cache = None
            return True
        except Exception as e:
            logger.error(f"Error guardando notificaciones: {e}")
            return False

    # ==================== AVANZADO (92 parámetros) ====================

    def get_advanced_settings(self) -> dict:
        """Retorna TODOS los 92 parámetros avanzados"""
        logger.debug(f"⚙️ [get_adv] cache_hit={self._advanced_settings_cache is not None}")
        if self._advanced_settings_cache is not None:
            return dict(self._advanced_settings_cache)

        s = self._settings

        settings = {
            # ==================== FPS / RENDIMIENTO ====================
            "target_fps": s.value("advanced/target_fps", 30, type=int),
            "screen_max_fps": s.value("advanced/screen_max_fps", 30, type=int),
            "force_camera_fps": s.value("advanced/force_camera_fps", False, type=bool),
            "buffer_size": s.value("advanced/buffer_size", 1, type=int),

            # ==================== THROTTLE ====================
            "throttle_enabled": s.value("advanced/throttle_enabled", True, type=bool),
            "throttle_target_cpu": s.value("advanced/throttle_target_cpu", 1.5, type=float),
            "throttle_target_gpu": s.value("advanced/throttle_target_gpu", 0.80, type=float),
            "throttle_max_skip": s.value("advanced/throttle_max_skip", 3, type=int),
            "throttle_check_interval": s.value("advanced/throttle_check_interval", 1.0, type=float),
            "throttle_hysteresis": s.value("advanced/throttle_hysteresis", 0.30, type=float),
            "throttle_gpu_measure_sample": s.value("advanced/throttle_gpu_measure_sample", 5, type=int),

            # ==================== DETECCIÓN MOVIMIENTO ====================
            "detection_frame_skip": s.value("advanced/detection_frame_skip", 3, type=int),
            "motion_method": s.value("advanced/motion_method", "adaptive", type=str),
            "motion_use_shadow_removal": s.value("advanced/motion_use_shadow_removal", True, type=bool),
            "motion_use_shape_filter": s.value("advanced/motion_use_shape_filter", True, type=bool),
            "motion_min_density": s.value("advanced/motion_min_density", 0.3, type=float),
            "motion_min_consecutive_frames": s.value("advanced/motion_min_consecutive_frames", 2, type=int),
            "motion_learning_rate": s.value("advanced/motion_learning_rate", 0.001, type=float),
            "motion_reinit_interval": s.value("advanced/motion_reinit_interval", 10.0, type=float),
            "motion_history": s.value("advanced/motion_history", 500, type=int),
            "motion_var_threshold": s.value("advanced/motion_var_threshold", 16, type=int),
            "motion_blur_size": s.value("advanced/motion_blur_size", 5, type=int),
            "motion_max_width_resize": s.value("advanced/motion_max_width_resize", 640, type=int),
            "motion_iou_threshold": s.value("advanced/motion_iou_threshold", 0.3, type=float),
            "motion_max_aspect_ratio": s.value("advanced/motion_max_aspect_ratio", 5, type=int),
            "motion_dilate_iterations": s.value("advanced/motion_dilate_iterations", 2, type=int),
            "motion_max_area_ratio": s.value("advanced/motion_max_area_ratio", 0.7, type=float),
            "motion_knn_dist2_threshold": s.value("advanced/motion_knn_dist2_threshold", 400, type=int),

            # ==================== FACIAL ====================
            "face_detector_model": s.value("advanced/face_detector_model", "sface", type=str),
            "face_auto_register_unknown": s.value("advanced/face_auto_register_unknown", True, type=bool),
            "face_min_face_size": s.value("advanced/face_min_face_size", 20, type=int),
            "face_recognition_scale": s.value("advanced/face_recognition_scale", 0.25, type=float),
            "face_detector_score_threshold": s.value("advanced/face_detector_score_threshold", 0.9, type=float),
            "face_nms_threshold": s.value("advanced/face_nms_threshold", 0.3, type=float),
            "face_top_k": s.value("advanced/face_top_k", 5000, type=int),
            "face_sface_threshold": s.value("advanced/face_sface_threshold", 0.363, type=float),
            "face_input_size": s.value("advanced/face_input_size", 320, type=int),

            # ==================== GRABACIÓN ====================
            "record_audio": s.value("advanced/record_audio", True, type=bool),
            "av_recorder_backend": s.value("advanced/av_recorder_backend", "auto", type=str),
            "auto_reencode_wrong_fps": s.value("advanced/auto_reencode_wrong_fps", False, type=bool),
            "auto_reencode_threshold": s.value("advanced/auto_reencode_threshold", 50.0, type=float),
            "record_auto_stop_after": s.value("advanced/record_auto_stop_after", 0, type=int),
            "video_crf": s.value("advanced/video_crf", 23, type=int),
            "video_preset": s.value("advanced/video_preset", "fast", type=str),
            "audio_blocksize": s.value("advanced/audio_blocksize", 1024, type=int),
            "audio_max_buffer_seconds": s.value("advanced/audio_max_buffer_seconds", 2.0, type=float),
            "reencode_timeout": s.value("advanced/reencode_timeout", 120, type=int),

            # ==================== AUDIO ====================
            "audio_sample_rate": s.value("advanced/audio_sample_rate", 44100, type=int),
            "audio_channels": s.value("advanced/audio_channels", 1, type=int),
            "audio_volume": s.value("advanced/audio_volume", 0.7, type=float),
            "audio_detect_endpoint": s.value("advanced/audio_detect_endpoint", True, type=bool),
            "audio_endpoints_priority": s.value("advanced/audio_endpoints_priority", "wav,pcm", type=str),

            # ==================== RED ====================
            "connection_timeout": s.value("advanced/connection_timeout", 2.0, type=float),
            "read_timeout": s.value("advanced/read_timeout", 2.0, type=float),
            "reconnect_delay": s.value("advanced/reconnect_delay", 0.5, type=float),
            "reconnect_attempts": s.value("advanced/reconnect_attempts", 3, type=int),
            "frame_timeout": s.value("advanced/frame_timeout", 5.0, type=float),

            # ==================== ESCANEO ====================
            "scan_frame_skip": s.value("advanced/scan_frame_skip", 5, type=int),

            # ==================== SISTEMA ====================
            "system_monitor_interval": s.value("advanced/system_monitor_interval", 1.0, type=float),
            "system_monitor_gpu_index": s.value("advanced/system_monitor_gpu_index", 0, type=int),
            "video_thumbnail_workers": s.value("advanced/video_thumbnail_workers", 2, type=int),
            "video_thumbnail_size": s.value("advanced/video_thumbnail_size", 160, type=int),
            "thumbnail_cache_enabled": s.value("advanced/thumbnail_cache_enabled", True, type=bool),
            "local_max_devices_detect": s.value("advanced/local_max_devices_detect", 5, type=int),

            # ==================== UI ====================
            "camera_widget_min_width": s.value("advanced/camera_widget_min_width", 320, type=int),
            "camera_widget_min_height": s.value("advanced/camera_widget_min_height", 280, type=int),
            "camera_widget_max_width": s.value("advanced/camera_widget_max_width", 480, type=int),
            "camera_widget_max_height": s.value("advanced/camera_widget_max_height", 400, type=int),
            "loading_overlay_timeout": s.value("advanced/loading_overlay_timeout", 500, type=int),
            "camera_display_fps": s.value("advanced/camera_display_fps", 30, type=int),
            "camera_fps_check_interval": s.value("advanced/camera_fps_check_interval", 1000, type=int),
            "recording_update_interval": s.value("advanced/recording_update_interval", 1000, type=int),
            "pixmap_pool_size": s.value("advanced/pixmap_pool_size", 3, type=int),
            "anim_duration_ms": s.value("advanced/anim_duration_ms", 350, type=int),
            "grid_spacing": s.value("advanced/grid_spacing", 12, type=int),
            "grid_margins": s.value("advanced/grid_margins", 8, type=int),
            "audio_meter_interval": s.value("advanced/audio_meter_interval", 50, type=int),

            # ==================== VIDEO PREVIEW ====================
            "thumbnail_frame_position": s.value("advanced/thumbnail_frame_position", 0.25, type=float),
            "video_default_volume": s.value("advanced/video_default_volume", 0.7, type=float),
            "seek_step_small": s.value("advanced/seek_step_small", 5, type=int),
            "seek_step_big": s.value("advanced/seek_step_big", 30, type=int),
            "step_frame_ms": s.value("advanced/step_frame_ms", 33, type=int),

            # ==================== MAIN WINDOW ====================
            "auto_capture_interval": s.value("advanced/auto_capture_interval", 5000, type=int),
            "flash_on_duration_ms": s.value("advanced/flash_on_duration_ms", 2000, type=int),
            "flash_off_duration_ms": s.value("advanced/flash_off_duration_ms", 1000, type=int),
            "loading_timeout": s.value("advanced/loading_timeout", 500, type=int),

            # ==================== NOTIFICACIONES ====================
            "notification_min_interval": s.value("advanced/notification_min_interval", 30, type=int),
            "telegram_send_timeout": s.value("advanced/telegram_send_timeout", 10, type=int),
            "telegram_photo_timeout": s.value("advanced/telegram_photo_timeout", 30, type=int),
            "windows_notification_duration": s.value("advanced/windows_notification_duration", 5, type=int),

            # ==================== FILE MANAGER ====================
            "image_interpolation": s.value("advanced/image_interpolation", "linear", type=str),
            "video_interpolation": s.value("advanced/video_interpolation", "linear", type=str),

            # ==================== SPLASH / LOADING OVERLAY ====================
            "loading_dots_interval": s.value("advanced/loading_dots_interval", 400, type=int),
            "loading_spinner_interval": s.value("advanced/loading_spinner_interval", 500, type=int),
            "loading_fade_duration": s.value("advanced/loading_fade_duration", 200, type=int),
            "splash_fade_in_duration": s.value("advanced/splash_fade_in_duration", 400, type=int),
            "splash_fade_out_duration": s.value("advanced/splash_fade_out_duration", 300, type=int),

            # ==================== GPU ====================
            "gpu_acceleration": s.value("advanced/gpu_acceleration", False, type=bool),

            # ==================== DEBUG ====================
            "debug_mode": s.value("advanced/debug_mode", False, type=bool),
            "save_logs": s.value("advanced/save_logs", True, type=bool),
            "log_level": s.value("advanced/log_level", "INFO", type=str),

            # ==================== INICIO ====================
            "auto_start": s.value("advanced/auto_start", False, type=bool),
            "remember_last_state": s.value("advanced/remember_last_state", True, type=bool),

            # ==================== SANDBOX ====================
            "sandbox_enabled": s.value("advanced/sandbox_enabled", False, type=bool),
            "sandbox_strict": s.value("advanced/sandbox_strict", True, type=bool),
        }

        self._advanced_settings_cache = settings
        logger.debug(f"⚙️ Cargados {len(settings)} parámetros avanzados")
        return dict(settings)

    def save_advanced_settings(self, settings: dict) -> bool:
        """Guarda TODOS los parámetros avanzados"""
        import time
        t0 = time.perf_counter()
        try:
            s = self._settings
            failed = []
            for key, value in settings.items():
                try:
                    s.setValue(f"advanced/{key}", value)
                except Exception as e:
                    failed.append((key, str(e)))

            s.sync()
            elapsed_ms = (time.perf_counter() - t0) * 1000
            self._advanced_settings_cache = None

            if failed:
                logger.error(
                    f"❌ [save_adv] {len(failed)}/{len(settings)} params fallaron: "
                    f"{failed[:5]}"
                )
                return False

            logger.debug(
                f"💾 [save_adv] {len(settings)} params en {elapsed_ms:.0f}ms"
            )
            return True
        except Exception as e:
            logger.error(f"❌ [save_adv] FALLÓ: {type(e).__name__}: {e}", exc_info=True)
            return False

    def get_advanced_param(self, key: str, default=None) -> Any:
        """Obtiene un solo parámetro avanzado (sin cargar todos)"""
        if default is None:
            from utils.config_loader import AdvancedConfig
            default = AdvancedConfig.DEFAULTS.get(key)

        # Detectar tipo desde el default
        if isinstance(default, bool):
            return self._settings.value(f"advanced/{key}", default, type=bool)
        elif isinstance(default, int):
            return self._settings.value(f"advanced/{key}", default, type=int)
        elif isinstance(default, float):
            return self._settings.value(f"advanced/{key}", default, type=float)
        else:
            return self._settings.value(f"advanced/{key}", default, type=str)

    # ==================== UI ====================

    def get_ui_settings(self) -> dict:
        if self._ui_settings_cache is not None:
            return dict(self._ui_settings_cache)

        settings = {
            "geometry": self._settings.value("ui/geometry", b""),
            "theme": self._settings.value("ui/theme", "dark", type=str),
            "camera_grid_columns": self._settings.value("ui/camera_grid_columns", 2, type=int)
        }
        self._ui_settings_cache = settings
        return dict(settings)

    def save_ui_settings(self, ui_settings: dict) -> bool:
        try:
            if "geometry" in ui_settings:
                self._settings.setValue("ui/geometry", ui_settings["geometry"])
            if "theme" in ui_settings:
                self._settings.setValue("ui/theme", ui_settings["theme"])
            if "camera_grid_columns" in ui_settings:
                self._settings.setValue("ui/camera_grid_columns", ui_settings["camera_grid_columns"])

            self._settings.sync()
            self._ui_settings_cache = None
            return True
        except Exception as e:
            logger.error(f"Error guardando UI: {e}")
            return False

    # ==================== UTILIDADES ====================

    def clear_all(self) -> bool:
        """Limpia toda la configuración"""
        try:
            self._settings.clear()
            self._settings.sync()
            self._invalidate_all_caches()
            logger.info("🗑️ Configuración limpiada")
            return True
        except Exception as e:
            logger.error(f"Error limpiando configuración: {e}")
            return False

    def _invalidate_all_caches(self):
        """Invalida todos los caches"""
        self._cameras_cache = None
        self._capture_settings_cache = None
        self._detection_settings_cache = None
        self._scan_settings_cache = None
        self._notification_settings_cache = None
        self._advanced_settings_cache = None
        self._ui_settings_cache = None

    def invalidate_cameras_cache(self):
        """Invalida cache de cámaras"""
        self._cameras_cache = None

    def invalidate_advanced_cache(self):
        """Invalida cache de avanzado"""
        self._advanced_settings_cache = None

    def invalidate_detection_cache(self):
        """Invalida cache de detección"""
        self._detection_settings_cache = None

    def invalidate_scan_cache(self):
        """Invalida cache de escaneo"""
        self._scan_settings_cache = None

    def invalidate_notification_cache(self):
        """Invalida cache de notificaciones"""
        self._notification_settings_cache = None

    def invalidate_capture_cache(self):
        """Invalida cache de captura"""
        self._capture_settings_cache = None

    def invalidate_ui_cache(self):
        """Invalida cache de UI"""
        self._ui_settings_cache = None


# Singleton global
settings_manager = SettingsManager()