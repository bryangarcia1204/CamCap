"""
DocumentAnalyzer — FrameAnalyzer para escaneo de documentos.

Envuelve ScanManager. Aplica scan_frame_skip propio porque
el escaneo es COSTOSO (detección + OCR).

⚠️ Este analyzer corre en el hilo worker y bloquea el frame.
Se recomienda usar scan_frame_skip >= 5.
"""
import time
from typing import Dict, Any, Optional
import numpy as np

from utils.logger import get_logger

logger = get_logger("DocumentAnalyzer")


class DocumentAnalyzer:
    """FrameAnalyzer que envuelve ScanManager."""

    _ENABLED_CHECK_INTERVAL = 2.0
    _CONFIG_REFRESH_INTERVAL = 5.0

    def __init__(self, context):
        self.context = context
        self._scanners: Dict[int, Any] = {}
        self._enabled_cache: Dict[int, bool] = {}
        self._last_check: Dict[int, float] = {}
        self._frame_counters: Dict[int, int] = {}
        self._config_cache: Optional[Dict[str, Any]] = None
        self._config_last_load: float = 0.0
        logger.debug("🔧 [init] DocumentAnalyzer creado")

    def should_run(self, camera_id: int) -> bool:
        now = time.time()
        if now - self._last_check.get(camera_id, 0) < self._ENABLED_CHECK_INTERVAL:
            enabled = self._enabled_cache.get(camera_id, False)
        else:
            try:
                from core.settings_manager import settings_manager
                scan = settings_manager.get_scan_settings()
                enabled = bool(scan.get("enabled", False))
            except Exception as e:
                logger.debug(f"Error leyendo scan.enabled: {e}")
                enabled = False
            self._enabled_cache[camera_id] = enabled
            self._last_check[camera_id] = now

        if not enabled:
            return False

        # Aplicar scan_frame_skip
        skip = self._get_scan_skip()
        counter = self._frame_counters.get(camera_id, 0) + 1
        self._frame_counters[camera_id] = counter
        return counter % max(1, skip) == 0

    def analyze(self, camera_id: int, frame: np.ndarray) -> Optional[Dict[str, Any]]:
        if frame is None or frame.size == 0:
            return None

        scanner = self._get_scanner(camera_id)
        if scanner is None:
            return None

        # Auto_correct desde scan_settings
        auto_correct = True
        try:
            from core.settings_manager import settings_manager
            scan = settings_manager.get_scan_settings()
            auto_correct = scan.get("auto_correct", True)
        except Exception:
            pass

        try:
            result = scanner.process_frame(frame, auto_correct=auto_correct)
        except Exception as e:
            logger.error(
                f"❌ Error en ScanManager (cámara {camera_id}): {e}",
                exc_info=True,
            )
            return None

        # Devolvemos uno u otro según el contenido
        if result.get("text"):
            return {
                "kind": "text",
                "camera_id": camera_id,
                "text": result["text"],
                "document_found": result.get("document_found", False),
                "confidence": result.get("confidence", 0.0),
                "ocr_confidence": result.get("ocr_confidence", 0.0),
            }
        if result.get("document_found"):
            return {
                "kind": "document",
                "camera_id": camera_id,
                "document_found": True,
                "confidence": result.get("confidence", 0.0),
                "corners": result.get("corners"),
            }
        return None

    def get_frame_skip(self) -> int:
        return self._get_scan_skip()

    def _get_scan_skip(self) -> int:
        cfg = self._get_config()
        return int(cfg.get("scan_frame_skip", 5))

    def _get_config(self) -> Dict[str, Any]:
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

    def _get_scanner(self, camera_id: int):
        if camera_id in self._scanners:
            return self._scanners[camera_id]
        try:
            from .scan_manager import ScanManager
            from core.settings_manager import settings_manager
            scan = settings_manager.get_scan_settings()
            tesseract_path = scan.get("tesseract_path") or None
            scanner = ScanManager(tesseract_path=tesseract_path)
            self._scanners[camera_id] = scanner
            logger.info(f"✅ ScanManager creado para cámara {camera_id}")
            return scanner
        except Exception as e:
            logger.error(
                f"❌ Error creando ScanManager para cámara {camera_id}: {e}",
                exc_info=True,
            )
            return None

    def reload_config(self):
        self._config_cache = None
        self._config_last_load = 0.0
        self._enabled_cache.clear()
        self._last_check.clear()
        self._frame_counters.clear()
        for camera_id, scanner in self._scanners.items():
            try:
                if hasattr(scanner, "reload_config"):
                    scanner.reload_config()
            except Exception as e:
                logger.debug(f"Error reload scanner {camera_id}: {e}")
        logger.info("🔄 DocumentAnalyzer recargado")

    def cleanup(self, camera_id: Optional[int] = None):
        if camera_id is not None:
            self._scanners.pop(camera_id, None)
            self._enabled_cache.pop(camera_id, None)
            self._last_check.pop(camera_id, None)
            self._frame_counters.pop(camera_id, None)
        else:
            self._scanners.clear()
            self._enabled_cache.clear()
            self._last_check.clear()
            self._frame_counters.clear()