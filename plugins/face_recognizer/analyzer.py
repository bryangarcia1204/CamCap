"""
FaceAnalyzer — FrameAnalyzer para reconocimiento facial.

Envuelve FaceRecognizer. Aplica cooldown de 1.5s por cámara
para no saturar el reconocimiento.
"""
import time
from typing import Dict, Any, Optional
import numpy as np

from utils.logger import get_logger

logger = get_logger("FaceAnalyzer")


class FaceAnalyzer:
    """FrameAnalyzer que envuelve FaceRecognizer."""

    _ENABLED_CHECK_INTERVAL = 2.0
    _RECOGNITION_COOLDOWN = 1.5

    def __init__(self, context):
        self.context = context
        self._recognizers: Dict[int, Any] = {}
        self._enabled_cache: Dict[int, bool] = {}
        self._last_check: Dict[int, float] = {}
        self._last_recognition: Dict[int, float] = {}
        logger.debug("🔧 [init] FaceAnalyzer creado")

    def should_run(self, camera_id: int) -> bool:
        now = time.time()
        if now - self._last_check.get(camera_id, 0) < self._ENABLED_CHECK_INTERVAL:
            return self._enabled_cache.get(camera_id, False)
        try:
            from core.settings_manager import settings_manager
            det = settings_manager.get_detection_settings()
            enabled = bool(det.get("face_enabled", False))
        except Exception as e:
            logger.debug(f"Error leyendo face_enabled: {e}")
            enabled = False
        self._enabled_cache[camera_id] = enabled
        self._last_check[camera_id] = now
        return enabled

    def analyze(self, camera_id: int, frame: np.ndarray) -> Optional[Dict[str, Any]]:
        if frame is None or frame.size == 0:
            return None

        # Cooldown de reconocimiento
        now = time.time()
        if now - self._last_recognition.get(camera_id, 0) < self._RECOGNITION_COOLDOWN:
            return None
        self._last_recognition[camera_id] = now

        recognizer = self._get_recognizer(camera_id)
        if recognizer is None or not recognizer.is_available():
            return None

        try:
            locations, names = recognizer.recognize(frame)
        except Exception as e:
            logger.error(
                f"❌ Error en FaceRecognizer (cámara {camera_id}): {e}",
                exc_info=True,
            )
            return None

        if not names:
            return None

        return {
            "kind": "face",
            "camera_id": camera_id,
            "locations": locations,
            "names": names,
        }

    def get_frame_skip(self) -> int:
        # Face ya tiene cooldown interno, no necesita frame skip extra
        return 1

    def _get_recognizer(self, camera_id: int):
        if camera_id in self._recognizers:
            return self._recognizers[camera_id]
        try:
            from .face_recognizer import FaceRecognizer
            from core.settings_manager import settings_manager
            det = settings_manager.get_detection_settings()
            recognizer = FaceRecognizer(
                tolerance=det.get("face_tolerance", 0.6),
            )
            self._recognizers[camera_id] = recognizer
            logger.info(
                f"✅ FaceRecognizer creado para cámara {camera_id} "
                f"(available={recognizer.is_available()})"
            )
            return recognizer
        except Exception as e:
            logger.error(
                f"❌ Error creando FaceRecognizer para cámara {camera_id}: {e}",
                exc_info=True,
            )
            return None

    def reload_config(self):
        self._enabled_cache.clear()
        self._last_check.clear()
        self._last_recognition.clear()
        for camera_id, recognizer in self._recognizers.items():
            try:
                if hasattr(recognizer, "reload_config"):
                    recognizer.reload_config()
            except Exception as e:
                logger.debug(f"Error reload recognizer {camera_id}: {e}")
        logger.info("🔄 FaceAnalyzer recargado")

    def cleanup(self, camera_id: Optional[int] = None):
        if camera_id is not None:
            self._recognizers.pop(camera_id, None)
            self._enabled_cache.pop(camera_id, None)
            self._last_check.pop(camera_id, None)
            self._last_recognition.pop(camera_id, None)
        else:
            self._recognizers.clear()
            self._enabled_cache.clear()
            self._last_check.clear()
            self._last_recognition.clear()