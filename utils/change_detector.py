"""
Detector granular de cambios de configuración.
Determina QUÉ se debe recargar y si es estructural o en caliente.
"""
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass, field
from enum import Enum

from utils.logger import get_logger

logger = get_logger("ChangeDetector")


class ReloadLevel(Enum):
    """Nivel de recarga necesario"""
    NONE = 0            # No hacer nada
    CONFIG_ONLY = 1     # Solo advanced_config.reload()
    HOT_RELOAD = 2      # Propagar a módulos en caliente
    RESTART_AFFECTED = 3  # Reiniciar solo cámaras afectadas
    RESTART_ALL = 4     # Reiniciar todo


@dataclass
class ChangeReport:
    """Reporte de cambios detectados"""
    level: ReloadLevel = ReloadLevel.NONE
    categories: List[str] = field(default_factory=list)
    affected_cameras: List[int] = field(default_factory=list)
    reason: str = ""

    def __repr__(self):
        return (f"ChangeReport(level={self.level.name}, "
                f"categories={self.categories}, "
                f"affected_cameras={self.affected_cameras}, "
                f"reason={self.reason!r})")


class ChangeDetector:
    """
    Analiza diferencias entre dos configuraciones y determina
    el nivel de recarga necesario.
    """

    # ==================== CAMPOS POR CATEGORÍA ====================

    # Cambios que requieren REINICIO COMPLETO de todas las cámaras
    STRUCTURAL_GLOBAL = {
        # Red global
        "connection_timeout", "read_timeout", "reconnect_delay",
        "reconnect_attempts", "frame_timeout",
        # FPS global
        "target_fps", "screen_max_fps", "buffer_size",
        "force_camera_fps",
    }

    # Cambios que requieren reinicio SOLO de cámaras específicas
    STRUCTURAL_PER_CAMERA = {
        # (por ahora ninguno, pero útil para futuras extensiones)
        # Ej: si tuvieras FPS por cámara
    }

    # Cambios que se aplican EN CALIENTE sin reiniciar
    HOT_RELOAD = {
        # Activación de plugins de detección
        "motion_enabled", "face_enabled",
        # Throttle
        "throttle_enabled", "throttle_target_cpu", "throttle_target_gpu",
        "throttle_max_skip", "throttle_check_interval",
        "throttle_hysteresis", "throttle_gpu_measure_sample",

        # Motion detector
        "motion_method", "motion_use_shadow_removal",
        "motion_use_shape_filter", "motion_min_density",
        "motion_min_consecutive_frames", "motion_learning_rate",
        "motion_reinit_interval", "motion_history", "motion_var_threshold",
        "motion_blur_size", "motion_max_width_resize",
        "motion_iou_threshold", "motion_max_aspect_ratio",
        "motion_dilate_iterations", "motion_max_area_ratio",
        "motion_knn_dist2_threshold",

        # Face
        "face_detector_model", "face_auto_register_unknown",
        "face_min_face_size", "face_recognition_scale",
        "face_detector_score_threshold", "face_nms_threshold",
        "face_top_k", "face_sface_threshold", "face_input_size",

        # Detection skip
        "detection_frame_skip", "scan_frame_skip",

        # Recording (no afecta al stream, solo al guardado)
        "record_audio", "av_recorder_backend", "auto_reencode_wrong_fps",
        "auto_reencode_threshold", "record_auto_stop_after",
        "video_crf", "video_preset", "audio_blocksize",
        "audio_max_buffer_seconds", "reencode_timeout",

        # Audio
        "audio_sample_rate", "audio_channels", "audio_volume",
        "audio_detect_endpoint", "audio_endpoints_priority",
    }

    # Cambios que requieren recargar solo el ScanManager
    SCAN_ONLY = {
        "scan_frame_skip",
    }

    # Cambios que requieren recargar solo el detector de movimiento
    MOTION_ONLY = {
        "motion_enabled",
        "motion_method", "motion_use_shadow_removal",
        "motion_use_shape_filter", "motion_min_density",
        "motion_min_consecutive_frames", "motion_learning_rate",
        "motion_reinit_interval", "motion_history", "motion_var_threshold",
        "motion_blur_size", "motion_max_width_resize",
        "motion_iou_threshold", "motion_max_aspect_ratio",
        "motion_dilate_iterations", "motion_max_area_ratio",
        "motion_knn_dist2_threshold",
    }

    # Cambios que requieren recargar solo el FaceRecognizer
    FACE_ONLY = {
        "face_enabled",
        "face_detector_model", "face_auto_register_unknown",
        "face_min_face_size", "face_recognition_scale",
        "face_detector_score_threshold", "face_nms_threshold",
        "face_top_k", "face_sface_threshold", "face_input_size",
    }

    # Cambios que requieren recargar solo el Throttle
    THROTTLE_ONLY = {
        "throttle_enabled", "throttle_target_cpu", "throttle_target_gpu",
        "throttle_max_skip", "throttle_check_interval",
        "throttle_hysteresis", "throttle_gpu_measure_sample",
    }

    # Cambios que afectan a la UI (widget, grid, video preview, etc.)
    UI_ONLY = {
        "camera_widget_min_width", "camera_widget_min_height",
        "camera_widget_max_width", "camera_widget_max_height",
        "camera_display_fps", "camera_fps_check_interval",
        "recording_update_interval", "pixmap_pool_size",
        "anim_duration_ms", "grid_spacing", "grid_margins",
        "audio_meter_interval",
        "thumbnail_frame_position", "video_default_volume",
        "seek_step_small", "seek_step_big", "step_frame_ms",
        "loading_overlay_timeout",
        "loading_dots_interval", "loading_spinner_interval",
        "loading_fade_duration", "splash_fade_in_duration",
        "splash_fade_out_duration",
    }

    # Cambios que requieren recargar SOLO FileManager
    FILEMANAGER_ONLY = {
        "image_interpolation", "video_interpolation",
    }

    # Cambios que requieren recargar SOLO AudioManager
    AUDIO_ONLY = {
        "audio_sample_rate", "audio_channels", "audio_volume",
        "audio_detect_endpoint", "audio_endpoints_priority",
    }

    # Cambios que requieren recargar SOLO NotificationManager
    NOTIFICATIONS_ONLY = {
        "notification_min_interval", "telegram_send_timeout",
        "telegram_photo_timeout", "windows_notification_duration",
    }

    # Cambios que requieren recargar SOLO SystemMonitor
    SYSTEM_MONITOR_ONLY = {
        "system_monitor_interval", "system_monitor_gpu_index",
    }

    # Cambios que requieren recargar SOLO ThumbnailWorker
    THUMBNAIL_ONLY = {
        "video_thumbnail_workers", "video_thumbnail_size",
        "thumbnail_cache_enabled",
    }

    # ==================== API PÚBLICA ====================

    @classmethod
    def analyze(cls,
                old_advanced: Dict[str, Any],
                new_advanced: Dict[str, Any],
                old_detection: Optional[Dict[str, Any]] = None,
                new_detection: Optional[Dict[str, Any]] = None,
                old_capture: Optional[Any] = None,
                new_capture: Optional[Any] = None,
                old_scan: Optional[Dict[str, Any]] = None,
                new_scan: Optional[Dict[str, Any]] = None,
                camera_count_changed: bool = False) -> ChangeReport:
        """
        Analiza diferencias y determina el nivel de recarga.

        Args:
            old_advanced: dict de advanced_settings anterior
            new_advanced: dict de advanced_settings actual
            old_detection: dict de detection_settings anterior (opcional)
            new_detection: dict de detection_settings actual (opcional)
            old_capture: CaptureSettings anterior (opcional)
            new_capture: CaptureSettings actual (opcional)
            old_scan: dict de scan_settings anterior (opcional)
            new_scan: dict de scan_settings actual (opcional)
            camera_count_changed: True si cambió el número de cámaras

        Returns:
            ChangeReport con level, categories, reason
        """
        report = ChangeReport()

        # === 1. Detectar cambios por categoría ===
        changed_keys = cls._diff_dicts(old_advanced, new_advanced)

        # Añadir cambios de detection_settings
        if old_detection is not None and new_detection is not None:
            changed_detection = cls._diff_dicts(old_detection, new_detection)
            # Mapear campos de detection a categorías
            for key in changed_detection:
                if key.startswith("motion_"):
                    if "motion" not in report.categories:
                        report.categories.append("motion")
                elif key.startswith("face_"):
                    if "face" not in report.categories:
                        report.categories.append("face")

        # Añadir cambios de scan_settings
        if old_scan is not None and new_scan is not None:
            changed_scan = cls._diff_dicts(old_scan, new_scan)
            if changed_scan and "scan" not in report.categories:
                report.categories.append("scan")

        # === 2. Analizar cada key cambiado ===
        for key in changed_keys:
            cls._classify_key(key, report)

        # === 3. Detectar cambio estructural por CaptureSettings ===
        capture_structural = False
        if old_capture is not None and new_capture is not None:
            if (old_capture.video_resolution != new_capture.video_resolution or
                    old_capture.video_fps != new_capture.video_fps or
                    old_capture.video_codec != new_capture.video_codec):
                capture_structural = True
                report.reason = "CaptureSettings estructurales cambiaron"
                logger.info(f"📊 Cambio estructural en CaptureSettings")

        # === 4. Determinar nivel final ===
        if camera_count_changed:
            report.level = ReloadLevel.RESTART_ALL
            report.reason = "Número de cámaras cambió"
            logger.info(f"🔴 Nivel RESTART_ALL: {report.reason}")

        elif capture_structural:
            report.level = ReloadLevel.RESTART_ALL
            report.reason = "CaptureSettings estructurales cambiaron"
            logger.info(f"🔴 Nivel RESTART_ALL: {report.reason}")

        elif cls._has_structural_global(changed_keys):
            report.level = ReloadLevel.RESTART_ALL
            report.reason = "Parámetros estructurales globales cambiaron"
            logger.info(f"🔴 Nivel RESTART_ALL: {report.reason}")

        elif cls._has_hot_reload(changed_keys):
            report.level = ReloadLevel.HOT_RELOAD
            report.reason = "Cambios aplicables en caliente"
            logger.info(f"🟢 Nivel HOT_RELOAD: {report.reason}")

        elif changed_keys or report.categories:
            report.level = ReloadLevel.CONFIG_ONLY
            report.reason = "Solo recargar config"
            logger.info(f"🟡 Nivel CONFIG_ONLY: {report.reason}")

        else:
            report.level = ReloadLevel.NONE
            report.reason = "Sin cambios"

        logger.info(f"📋 ChangeReport: {report}")
        return report

    @classmethod
    def analyze_detailed(cls,
                         old_advanced: Dict[str, Any],
                         new_advanced: Dict[str, Any],
                         old_detection: Optional[Dict[str, Any]] = None,
                         new_detection: Optional[Dict[str, Any]] = None,
                         old_capture: Optional[Any] = None,
                         new_capture: Optional[Any] = None,
                         old_scan: Optional[Dict[str, Any]] = None,
                         new_scan: Optional[Dict[str, Any]] = None,
                         camera_count_changed: bool = False) -> Tuple[ChangeReport, Dict[str, List[str]]]:
        """
        Retorna el reporte Y un diccionario con qué módulos recargar.

        Returns:
            (report, modules_to_reload)
            donde modules_to_reload es:
            {
                "motion": ["motion_method", "motion_blur_size", ...],
                "face": ["face_detector_model", ...],
                "scan": [...],
                "throttle": [...],
                "ui": [...],
                "file_manager": [...],
                "audio": [...],
                "notifications": [...],
                "system_monitor": [...],
                "thumbnail": [...],
            }
        """
        report = cls.analyze(
            old_advanced, new_advanced,
            old_detection, new_detection,
            old_capture, new_capture,
            old_scan, new_scan,
            camera_count_changed
        )

        # Detectar cambios por módulo
        changed_keys = cls._diff_dicts(old_advanced, new_advanced)
        modules = {}

        for key in changed_keys:
            # Determinar a qué módulos afecta
            if key in cls.MOTION_ONLY:
                modules.setdefault("motion", []).append(key)
            if key in cls.FACE_ONLY:
                modules.setdefault("face", []).append(key)
            if key in cls.SCAN_ONLY:
                modules.setdefault("scan", []).append(key)
            if key in cls.THROTTLE_ONLY:
                modules.setdefault("throttle", []).append(key)
            if key in cls.UI_ONLY:
                modules.setdefault("ui", []).append(key)
            if key in cls.FILEMANAGER_ONLY:
                modules.setdefault("file_manager", []).append(key)
            if key in cls.AUDIO_ONLY:
                modules.setdefault("audio", []).append(key)
            if key in cls.NOTIFICATIONS_ONLY:
                modules.setdefault("notifications", []).append(key)
            if key in cls.SYSTEM_MONITOR_ONLY:
                modules.setdefault("system_monitor", []).append(key)
            if key in cls.THUMBNAIL_ONLY:
                modules.setdefault("thumbnail", []).append(key)

        return report, modules

    # ==================== HELPERS PRIVADOS ====================

    @staticmethod
    def _diff_dicts(old: Dict[str, Any], new: Dict[str, Any]) -> List[str]:
        """Retorna lista de keys que cambiaron"""
        changed = []
        all_keys = set(old.keys()) | set(new.keys())
        for key in all_keys:
            if old.get(key) != new.get(key):
                changed.append(key)
        return changed

    @classmethod
    def _classify_key(cls, key: str, report: ChangeReport):
        """Clasifica una key cambiada en categorías"""
        # Verificar categorías existentes
        if key in cls.MOTION_ONLY and "motion" not in report.categories:
            report.categories.append("motion")
        if key in cls.FACE_ONLY and "face" not in report.categories:
            report.categories.append("face")
        if key in cls.SCAN_ONLY and "scan" not in report.categories:
            report.categories.append("scan")
        if key in cls.THROTTLE_ONLY and "throttle" not in report.categories:
            report.categories.append("throttle")
        if key in cls.UI_ONLY and "ui" not in report.categories:
            report.categories.append("ui")
        if key in cls.FILEMANAGER_ONLY and "file_manager" not in report.categories:
            report.categories.append("file_manager")
        if key in cls.AUDIO_ONLY and "audio" not in report.categories:
            report.categories.append("audio")
        if key in cls.NOTIFICATIONS_ONLY and "notifications" not in report.categories:
            report.categories.append("notifications")
        if key in cls.SYSTEM_MONITOR_ONLY and "system_monitor" not in report.categories:
            report.categories.append("system_monitor")
        if key in cls.THUMBNAIL_ONLY and "thumbnail" not in report.categories:
            report.categories.append("thumbnail")

    @classmethod
    def _has_structural_global(cls, changed_keys: List[str]) -> bool:
        """Verifica si hay cambios que requieren reinicio global"""
        return any(k in cls.STRUCTURAL_GLOBAL for k in changed_keys)

    @classmethod
    def _has_hot_reload(cls, changed_keys: List[str]) -> bool:
        """Verifica si hay cambios que se aplican en caliente"""
        return any(k in cls.HOT_RELOAD for k in changed_keys)