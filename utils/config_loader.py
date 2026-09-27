"""
Cargador de configuración avanzada centralizado.
Incluye TODOS los parámetros ajustables desde la UI (92).

Categorías:
  - FPS / Rendimiento
  - Throttle Adaptativo
  - Detección de Movimiento
  - Reconocimiento Facial
  - Grabación
  - Audio
  - Red
  - Escaneo
  - Sistema
  - UI
  - Video Preview
  - Main Window
  - Notificaciones
  - File Manager
  - Splash / Loading Overlay
  - GPU
  - Debug
  - Inicio
"""
from typing import Dict, Any
from utils.logger import get_logger

logger = get_logger("ConfigLoader")


class AdvancedConfig:
    """Configuración avanzada con valores por defecto seguros"""

    _instance = None
    _config: Dict[str, Any] = None

    DEFAULTS = {
        # ============================================================
        # FPS / RENDIMIENTO
        # ============================================================
        "target_fps": 30,
        "screen_max_fps": 30,
        "force_camera_fps": False,
        "buffer_size": 1,

        # ============================================================
        # THROTTLE ADAPTATIVO
        # ============================================================
        "throttle_enabled": True,
        "throttle_target_cpu": 1.5,
        "throttle_target_gpu": 0.80,
        "throttle_max_skip": 3,
        "throttle_check_interval": 1.0,
        "throttle_hysteresis": 0.30,
        "throttle_gpu_measure_sample": 5,

        # ============================================================
        # DETECCIÓN DE MOVIMIENTO
        # ============================================================
        # Básicos
        "detection_frame_skip": 3,
        "motion_method": "adaptive",
        "motion_use_shadow_removal": True,
        "motion_use_shape_filter": True,
        "motion_min_density": 0.3,
        "motion_min_consecutive_frames": 2,
        "motion_learning_rate": 0.001,
        "motion_reinit_interval": 10.0,
        "motion_history": 500,
        "motion_var_threshold": 16,
        # Avanzados
        "motion_blur_size": 5,
        "motion_max_width_resize": 640,
        "motion_iou_threshold": 0.3,
        "motion_max_aspect_ratio": 5,
        "motion_dilate_iterations": 2,
        "motion_max_area_ratio": 0.7,
        "motion_knn_dist2_threshold": 400,

        # ============================================================
        # RECONOCIMIENTO FACIAL
        # ============================================================
        # Básicos
        "face_detector_model": "sface",
        "face_auto_register_unknown": True,
        "face_min_face_size": 20,
        "face_recognition_scale": 0.25,
        "face_detector_score_threshold": 0.9,
        # Avanzados
        "face_nms_threshold": 0.3,
        "face_top_k": 5000,
        "face_sface_threshold": 0.363,
        "face_input_size": 320,

        # ============================================================
        # GRABACIÓN
        # ============================================================
        "record_audio": True,
        "av_recorder_backend": "auto",
        "auto_reencode_wrong_fps": False,
        "auto_reencode_threshold": 50.0,
        "record_auto_stop_after": 0,
        "video_crf": 23,
        "video_preset": "fast",
        "audio_blocksize": 1024,
        "audio_max_buffer_seconds": 2.0,
        "reencode_timeout": 120,

        # ============================================================
        # AUDIO
        # ============================================================
        "audio_sample_rate": 44100,
        "audio_channels": 1,
        "audio_volume": 0.7,
        "audio_detect_endpoint": True,
        "audio_endpoints_priority": "wav,pcm",

        # ============================================================
        # RED
        # ============================================================
        "connection_timeout": 2.0,
        "read_timeout": 2.0,
        "reconnect_delay": 0.5,
        "reconnect_attempts": 3,
        "frame_timeout": 5.0,

        # ============================================================
        # ESCANEO
        # ============================================================
        "scan_frame_skip": 5,

        # ============================================================
        # SISTEMA
        # ============================================================
        "system_monitor_interval": 1.0,
        "system_monitor_gpu_index": 0,
        "video_thumbnail_workers": 2,
        "video_thumbnail_size": 160,
        "thumbnail_cache_enabled": True,
        "local_max_devices_detect": 5,

        # ============================================================
        # UI
        # ============================================================
        "camera_widget_min_width": 320,
        "camera_widget_min_height": 280,
        "camera_widget_max_width": 480,
        "camera_widget_max_height": 400,
        "loading_overlay_timeout": 500,
        "camera_display_fps": 30,
        "camera_fps_check_interval": 1000,
        "recording_update_interval": 1000,
        "pixmap_pool_size": 3,
        "anim_duration_ms": 350,
        "grid_spacing": 12,
        "grid_margins": 8,
        "audio_meter_interval": 50,

        # ============================================================
        # VIDEO PREVIEW
        # ============================================================
        "thumbnail_frame_position": 0.25,
        "video_default_volume": 0.7,
        "seek_step_small": 5,
        "seek_step_big": 30,
        "step_frame_ms": 33,

        # ============================================================
        # MAIN WINDOW
        # ============================================================
        "auto_capture_interval": 5000,
        "flash_on_duration_ms": 2000,
        "flash_off_duration_ms": 1000,
        "loading_timeout": 500,

        # ============================================================
        # NOTIFICACIONES
        # ============================================================
        "notification_min_interval": 30,
        "telegram_send_timeout": 10,
        "telegram_photo_timeout": 30,
        "windows_notification_duration": 5,

        # ============================================================
        # FILE MANAGER
        # ============================================================
        "image_interpolation": "linear",
        "video_interpolation": "linear",

        # ============================================================
        # SPLASH / LOADING OVERLAY
        # ============================================================
        "loading_dots_interval": 400,
        "loading_spinner_interval": 500,
        "loading_fade_duration": 200,
        "splash_fade_in_duration": 400,
        "splash_fade_out_duration": 300,

        # ============================================================
        # GPU
        # ============================================================
        "gpu_acceleration": False,

        # ============================================================
        # DEBUG
        # ============================================================
        "debug_mode": False,
        "save_logs": True,
        "log_level": "INFO",

        # ============================================================
        # INICIO
        # ============================================================
        "auto_start": False,
        "remember_last_state": True,
    }

    # Categorías (útil para iterar y para la UI)
    CATEGORIES = {
        "performance": [
            "target_fps", "screen_max_fps", "force_camera_fps", "buffer_size",
        ],
        "throttle": [
            "throttle_enabled", "throttle_target_cpu", "throttle_target_gpu",
            "throttle_max_skip", "throttle_check_interval", "throttle_hysteresis",
            "throttle_gpu_measure_sample",
        ],
        "motion": [
            "detection_frame_skip", "motion_method", "motion_use_shadow_removal",
            "motion_use_shape_filter", "motion_min_density",
            "motion_min_consecutive_frames", "motion_learning_rate",
            "motion_reinit_interval", "motion_history", "motion_var_threshold",
            "motion_blur_size", "motion_max_width_resize",
            "motion_iou_threshold", "motion_max_aspect_ratio",
            "motion_dilate_iterations", "motion_max_area_ratio",
            "motion_knn_dist2_threshold",
        ],
        "face": [
            "face_detector_model", "face_auto_register_unknown",
            "face_min_face_size", "face_recognition_scale",
            "face_detector_score_threshold", "face_nms_threshold",
            "face_top_k", "face_sface_threshold", "face_input_size",
        ],
        "recording": [
            "record_audio", "av_recorder_backend", "auto_reencode_wrong_fps",
            "auto_reencode_threshold", "record_auto_stop_after",
            "video_crf", "video_preset", "audio_blocksize",
            "audio_max_buffer_seconds", "reencode_timeout",
        ],
        "audio": [
            "audio_sample_rate", "audio_channels", "audio_volume",
            "audio_detect_endpoint", "audio_endpoints_priority",
        ],
        "network": [
            "connection_timeout", "read_timeout", "reconnect_delay",
            "reconnect_attempts", "frame_timeout",
        ],
        "scan": ["scan_frame_skip"],
        "system": [
            "system_monitor_interval", "system_monitor_gpu_index",
            "video_thumbnail_workers", "video_thumbnail_size",
            "thumbnail_cache_enabled", "local_max_devices_detect",
        ],
        "ui": [
            "camera_widget_min_width", "camera_widget_min_height",
            "camera_widget_max_width", "camera_widget_max_height",
            "loading_overlay_timeout", "camera_display_fps",
            "camera_fps_check_interval", "recording_update_interval",
            "pixmap_pool_size", "anim_duration_ms",
            "grid_spacing", "grid_margins", "audio_meter_interval",
        ],
        "video_preview": [
            "thumbnail_frame_position", "video_default_volume",
            "seek_step_small", "seek_step_big", "step_frame_ms",
        ],
        "main_window": [
            "auto_capture_interval", "flash_on_duration_ms",
            "flash_off_duration_ms", "loading_timeout",
        ],
        "notifications": [
            "notification_min_interval", "telegram_send_timeout",
            "telegram_photo_timeout", "windows_notification_duration",
        ],
        "file_manager": [
            "image_interpolation", "video_interpolation",
        ],
        "splash": [
            "loading_dots_interval", "loading_spinner_interval",
            "loading_fade_duration", "splash_fade_in_duration",
            "splash_fade_out_duration",
        ],
        "hardware": ["gpu_acceleration"],
        "debug": ["debug_mode", "save_logs", "log_level"],
        "startup": ["auto_start", "remember_last_state"],
    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def load(cls) -> Dict[str, Any]:
        """Carga la configuración desde settings"""
        try:
            from core.settings_manager import settings_manager
            loaded = settings_manager.get_advanced_settings()

            # Combinar con defaults (por si faltan claves)
            cls._config = {**cls.DEFAULTS, **loaded}

            logger.info(
                f"⚙️ Config avanzada cargada ({len(cls._config)} params): "
                f"FPS={cls._config['target_fps']}, "
                f"screen_max={cls._config['screen_max_fps']}, "
                f"throttle_cpu={cls._config['throttle_target_cpu']}, "
                f"motion_method={cls._config['motion_method']}, "
                f"face_model={cls._config['face_detector_model']}"
            )
            return cls._config
        except Exception as e:
            logger.error(f"Error cargando config avanzada: {e}")
            cls._config = cls.DEFAULTS.copy()
            return cls._config

    @classmethod
    def get(cls, key: str, default=None) -> Any:
        """Obtiene un valor de config"""
        if cls._config is None:
            cls.load()
        return cls._config.get(
            key,
            default if default is not None else cls.DEFAULTS.get(key)
        )

    @classmethod
    def get_all(cls) -> Dict[str, Any]:
        """Retorna toda la configuración"""
        if cls._config is None:
            cls.load()
        return cls._config.copy()

    @classmethod
    def get_category(cls, category: str) -> Dict[str, Any]:
        """Retorna los parámetros de una categoría específica"""
        if cls._config is None:
            cls.load()
        keys = cls.CATEGORIES.get(category, [])
        return {k: cls._config.get(k) for k in keys}

    @classmethod
    def set(cls, key: str, value: Any) -> bool:
        """Establece un valor en memoria (no persiste)"""
        if cls._config is None:
            cls.load()
        if key in cls.DEFAULTS:
            cls._config[key] = value
            return True
        return False

    @classmethod
    def reload(cls) -> Dict[str, Any]:
        """Recarga desde settings"""
        return cls.load()

    @classmethod
    def count(cls) -> int:
        """Retorna el número total de parámetros"""
        return len(cls.DEFAULTS)

    @classmethod
    def list_all_keys(cls) -> list:
        """Retorna la lista de todas las claves"""
        return list(cls.DEFAULTS.keys())


# Instancia global
advanced_config = AdvancedConfig()