"""
MotionAnalyzer — Implementación de FrameAnalyzer para detección de movimiento.

Este analyzer envuelve el MotionDetector del plugin y expone una
interfaz unificada que el CameraThread consume sin saber que es
un plugin.

Flujo:
    CameraThread._process_detections()
      → registry.get(FrameAnalyzer)
      → analyzer.should_run(camera_id) → bool
      → analyzer.analyze(camera_id, frame) → dict
      → CameraThread emite señal según dict["kind"]

Threading:
    Los métodos corren en el hilo worker del CameraThread.
    El estado (detectors por cámara) es accedido solo por ese hilo.
    NO necesita locks.
"""
import time
from typing import Dict, Any, Optional, List
import numpy as np

from utils.logger import get_logger

logger = get_logger("MotionAnalyzer")


class MotionAnalyzer:
    """FrameAnalyzer que envuelve el MotionDetector del plugin."""

    # Cache de enabled por cámara (evita leer QSettings cada frame)
    _ENABLED_CHECK_INTERVAL = 2.0   # segundos

    def __init__(self, context):
        """
        Args:
            context: PluginContext (para acceder a settings, logger, etc.)
        """
        self.context = context

        # Estado por cámara
        self._detectors: Dict[int, Any] = {}
        self._enabled_cache: Dict[int, bool] = {}
        self._last_check: Dict[int, float] = {}

        # Config cache (evita leer advanced_config por frame)
        self._config_cache: Optional[Dict[str, Any]] = None
        self._config_last_load: float = 0.0
        self._CONFIG_REFRESH_INTERVAL = 5.0   # segundos

        logger.debug("🔧 [init] MotionAnalyzer creado")

    # ==================== API FrameAnalyzer ====================

    def should_run(self, camera_id: int) -> bool:
        """
        Retorna True si hay que analizar el frame de esta cámara.

        Lee `detection_settings.motion_enabled` con cache de 2s.
        """
        now = time.time()

        if now - self._last_check.get(camera_id, 0) < self._ENABLED_CHECK_INTERVAL:
            return self._enabled_cache.get(camera_id, False)

        try:
            from core.settings_manager import settings_manager
            det = settings_manager.get_detection_settings()
            enabled = bool(det.get("motion_enabled", False))
        except Exception as e:
            logger.debug(f"Error leyendo motion_enabled: {e}")
            enabled = False

        self._enabled_cache[camera_id] = enabled
        self._last_check[camera_id] = now
        return enabled

    def analyze(self, camera_id: int, frame: np.ndarray) -> Optional[Dict[str, Any]]:
        """
        Analiza el frame.

        Returns:
            dict con:
                - kind: "motion"
                - rects: List[Tuple[int,int,int,int]]
                - intensity: float (0-1)
                - notify: bool (True si pasó el cooldown)
            o None si no hay detector o frame inválido.
        """
        if frame is None or frame.size == 0:
            return None

        detector = self._get_detector(camera_id)
        if detector is None:
            return None

        try:
            has_motion, rects, _ = detector.detect(frame)
        except Exception as e:
            logger.error(
                f"❌ Error en MotionDetector (cámara {camera_id}): {e}",
                exc_info=True,
            )
            return None

        # Aplicar cooldown: notificar solo si pasó el cooldown
        notify = False
        if has_motion and detector.can_notify():
            notify = True

        return {
            "kind": "motion",
            "camera_id": camera_id,
            "rects": rects,
            "intensity": getattr(detector, "motion_intensity", 0.0),
            "notify": notify,
            "has_motion": has_motion,
        }

    def get_frame_skip(self) -> int:
        """Cuántos frames saltar entre análisis."""
        cfg = self._get_config()
        return int(cfg.get("detection_frame_skip", 3))

    # ==================== CONFIG (cacheada) ====================

    def _get_config(self) -> Dict[str, Any]:
        """Config cacheada de advanced_config (refresh cada 5s)."""
        now = time.time()
        if (self._config_cache is None or
                now - self._config_last_load > self._CONFIG_REFRESH_INTERVAL):
            try:
                from utils.config_loader import advanced_config
                self._config_cache = advanced_config.get_all()
                self._config_last_load = now
            except Exception as e:
                logger.debug(f"Error leyendo advanced_config: {e}")
                if self._config_cache is None:
                    self._config_cache = {}
        return self._config_cache

    # ==================== DETECTORES ====================

    def _get_detector(self, camera_id: int):
        """Obtiene (o crea) el MotionDetector para esta cámara."""
        if camera_id in self._detectors:
            return self._detectors[camera_id]

        try:
            from plugins.motion_detector.motion_detector import MotionDetector
            from core.settings_manager import settings_manager

            det = settings_manager.get_detection_settings()

            detector = MotionDetector(
                sensitivity=det.get("motion_sensitivity", 25),
                min_area=det.get("motion_min_area", 500),
                cooldown_seconds=det.get("motion_cooldown", 5.0),
            )
            self._detectors[camera_id] = detector

            logger.info(f"✅ MotionDetector creado para cámara {camera_id}")
            return detector

        except Exception as e:
            logger.error(
                f"❌ Error creando MotionDetector para cámara {camera_id}: {e}",
                exc_info=True,
            )
            return None

    # ==================== CLEANUP ====================

    def reload_config(self):
        """Fuerza recarga de config y aplica a todos los detectores."""
        self._config_cache = None
        self._config_last_load = 0.0
        self._enabled_cache.clear()
        self._last_check.clear()

        for camera_id, detector in self._detectors.items():
            try:
                if hasattr(detector, "reload_config"):
                    detector.reload_config()
            except Exception as e:
                logger.debug(f"Error reload detector {camera_id}: {e}")

        logger.info("🔄 MotionAnalyzer recargado")

    def cleanup(self, camera_id: Optional[int] = None):
        """
        Limpia detectors.
        Si camera_id es None, limpia todo.
        """
        if camera_id is not None:
            self._detectors.pop(camera_id, None)
            self._enabled_cache.pop(camera_id, None)
            self._last_check.pop(camera_id, None)
            logger.debug(f"🧹 MotionAnalyzer: detector {camera_id} eliminado")
        else:
            self._detectors.clear()
            self._enabled_cache.clear()
            self._last_check.clear()
            logger.debug("🧹 MotionAnalyzer: todos los detectores eliminados")

    def draw_motion_rects(self, camera_id: int, frame: np.ndarray,
                          rects: List = None) -> np.ndarray:
        """Delegado al detector. Para compatibilidad con MotionProcessor."""
        detector = self._detectors.get(camera_id)
        if detector is None:
            return frame
        return detector.draw_motion_rects(frame, rects)