"""
Detector de movimiento - v3
Todos los parámetros son ajustables desde la UI (advanced_config).
"""
import cv2
import numpy as np
import time
from typing import Optional, Tuple, List, Dict, Any
from utils.logger import get_logger
from utils.config_loader import advanced_config

logger = get_logger("MotionDetector")


class MotionDetector:
    """Detector de movimiento de alta precisión - Configurable"""

    # Cache compartido de CLAHE entre instancias
    _shared_clahe = None

    @classmethod
    def _get_clahe(cls):
        if cls._shared_clahe is None:
            cls._shared_clahe = cv2.createCLAHE(
                clipLimit=2.0, tileGridSize=(8, 8)
            )
        return cls._shared_clahe

    def __init__(self,
                 sensitivity: int = None,
                 min_area: int = None,
                 cooldown_seconds: float = None,
                 method: str = None,
                 learning_rate: float = None,
                 reinit_interval: float = None,
                 min_density: float = None,
                 min_consecutive_frames: int = None,
                 use_shadow_removal: bool = None,
                 use_shape_filter: bool = None,
                 history: int = None,
                 var_threshold: int = None):
        """
        Todos los parámetros se leen de advanced_config si no se pasan.
        """
        cfg = advanced_config.get_all()

        self.sensitivity = sensitivity if sensitivity is not None else 25
        self.min_area = min_area if min_area is not None else 500
        self.cooldown_seconds = cooldown_seconds if cooldown_seconds is not None else 5.0

        # Desde config
        self.method = method if method is not None else cfg.get("motion_method", "adaptive")
        self.learning_rate = learning_rate if learning_rate is not None else cfg.get("motion_learning_rate", 0.001)
        self.reinit_interval = reinit_interval if reinit_interval is not None else cfg.get("motion_reinit_interval", 10.0)
        self.min_density = min_density if min_density is not None else cfg.get("motion_min_density", 0.3)
        self.min_consecutive_frames = (
            min_consecutive_frames if min_consecutive_frames is not None
            else cfg.get("motion_min_consecutive_frames", 2)
        )
        self.use_shadow_removal = (
            use_shadow_removal if use_shadow_removal is not None
            else cfg.get("motion_use_shadow_removal", True)
        )
        self.use_shape_filter = (
            use_shape_filter if use_shape_filter is not None
            else cfg.get("motion_use_shape_filter", True)
        )
        self.history = history if history is not None else cfg.get("motion_history", 500)
        self.var_threshold = var_threshold if var_threshold is not None else cfg.get("motion_var_threshold", 16)

        # Estado
        self.blur_size = cfg.get("motion_blur_size", 5)
        self.max_width_resize = cfg.get("motion_max_width_resize", 640)
        self.iou_threshold = cfg.get("motion_iou_threshold", 0.3)
        self.max_aspect_ratio = cfg.get("motion_max_aspect_ratio", 5)
        self.dilate_iterations = cfg.get("motion_dilate_iterations", 2)
        self.max_area_ratio = cfg.get("motion_max_area_ratio", 0.7)
        self.knn_dist2_threshold = cfg.get("motion_knn_dist2_threshold", 400)
        self._last_detection_time = 0
        self._last_reinit_time = time.time()
        self._motion_frames_count = 0
        self._no_motion_frames_count = 0
        self.last_motion_rects = []
        self.total_detections = 0
        self.motion_intensity = 0.0

        # Frames previos para frame_diff
        self.previous_gray = None

        # Background subtractors
        self._create_bg_subtractors()

        # Kernels
        self.kernel_ellipse = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        self.kernel_rect = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))

        # 🔍 DEBUG: Estado inicial
        logger.debug(
            f"🔧 [init] MotionDetector: method={self.method}, "
            f"sens={self.sensitivity}, min_area={self.min_area}, "
            f"min_consecutive={self.min_consecutive_frames}, "
            f"learning_rate={self.learning_rate}, "
            f"reinit_interval={self.reinit_interval}s, "
            f"history={self.history}, var_threshold={self.var_threshold}"
        )

        logger.info(
            f"MotionDetector: method={self.method}, "
            f"min_consecutive={self.min_consecutive_frames}, "
            f"learning_rate={self.learning_rate}, "
            f"reinit_interval={self.reinit_interval}s"
        )

    def _create_bg_subtractors(self):
        """Crea los background subtractors según config"""
        self.bg_subtractor_mog2 = cv2.createBackgroundSubtractorMOG2(
            history=self.history,
            varThreshold=self.var_threshold,
            detectShadows=self.use_shadow_removal
        )
        self.bg_subtractor_knn = cv2.createBackgroundSubtractorKNN(
            history=self.history,
            dist2Threshold=self.knn_dist2_threshold,
            detectShadows=self.use_shadow_removal
        )

        # 🔍 DEBUG: Subtractors creados
        logger.debug(
            f"🔧 [bg_sub] MOG2+KNN creados: history={self.history}, "
            f"var_threshold={self.var_threshold}, "
            f"knn_dist2={self.knn_dist2_threshold}, "
            f"shadows={self.use_shadow_removal}"
        )

    def reload_config(self):
        """Recarga parámetros desde advanced_config"""
        from utils.config_loader import advanced_config
        cfg = advanced_config.get_all()

        self.method = cfg.get("motion_method", "adaptive")
        self.learning_rate = cfg.get("motion_learning_rate", 0.001)
        self.reinit_interval = cfg.get("motion_reinit_interval", 10.0)
        self.min_density = cfg.get("motion_min_density", 0.3)
        self.min_consecutive_frames = cfg.get("motion_min_consecutive_frames", 2)
        self.use_shadow_removal = cfg.get("motion_use_shadow_removal", True)
        self.use_shape_filter = cfg.get("motion_use_shape_filter", True)
        self.history = cfg.get("motion_history", 500)
        self.var_threshold = cfg.get("motion_var_threshold", 16)

        # Nuevos (16 faltantes)
        self.blur_size = cfg.get("motion_blur_size", 5)
        self.max_width_resize = cfg.get("motion_max_width_resize", 640)
        self.iou_threshold = cfg.get("motion_iou_threshold", 0.3)
        self.max_aspect_ratio = cfg.get("motion_max_aspect_ratio", 5)
        self.dilate_iterations = cfg.get("motion_dilate_iterations", 2)
        self.max_area_ratio = cfg.get("motion_max_area_ratio", 0.7)
        self.knn_dist2_threshold = cfg.get("motion_knn_dist2_threshold", 400)

        # Recrear bg subtractors
        self._create_bg_subtractors()

        # 🔍 DEBUG: Config recargada
        logger.debug(
            f"🔄 [reload] MotionDetector: method={self.method}, "
            f"blur={self.blur_size}, max_width={self.max_width_resize}, "
            f"iou={self.iou_threshold}, dilate={self.dilate_iterations}"
        )
        logger.info(f"🔄 MotionDetector recargado: {self.method}")
        return True

    def detect(self, frame: np.ndarray) -> Tuple[bool, List[Tuple], Optional[np.ndarray]]:
        """
        Detecta movimiento en un frame.
        Retorna (has_motion, rects, mask)
        """
        if frame is None or frame.size == 0:
            return False, [], None

        # Re-inicializar fondo periódicamente
        now = time.time()
        if now - self._last_reinit_time > self.reinit_interval:
            self._create_bg_subtractors()
            self._last_reinit_time = now
            logger.debug(f"🔄 [motion] Fondo re-inicializado")

        # Redimensionar para procesamiento
        height, width = frame.shape[:2]
        max_width = self.max_width_resize
        if width > max_width:
            scale = max_width / width
            small_frame = cv2.resize(frame, (max_width, int(height * scale)))
        else:
            scale = 1.0
            small_frame = frame

        # Preprocesamiento
        gray = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        gray = self._get_clahe().apply(gray)

        # Detección según método
        if self.method == "frame_diff":
            has_motion, rects, mask = self._detect_frame_diff(gray, scale, frame.shape)
        elif self.method == "mog2":
            has_motion, rects, mask = self._detect_mog2(gray, scale, frame.shape)
        else:  # adaptive
            has_motion, rects, mask = self._detect_adaptive(gray, scale, frame.shape)

        # Filtro de consecutividad
        if has_motion:
            self._motion_frames_count += 1
            self._no_motion_frames_count = 0
        else:
            self._no_motion_frames_count += 1
            self._motion_frames_count = max(0, self._motion_frames_count - 1)

        confirmed = self._motion_frames_count >= self.min_consecutive_frames

        # Calcular intensidad
        if confirmed and rects:
            total_area = sum(w * h for (_, _, w, h) in rects)
            frame_area = frame.shape[0] * frame.shape[1]
            self.motion_intensity = min(1.0, total_area / frame_area * 5)
            self.total_detections += 1
            self.last_motion_rects = rects

            logger.debug(
                f"🚶 [motion] CONFIRMADO: {len(rects)} rects, "
                f"área_total={total_area}px², intensidad={self.motion_intensity:.2f}"
            )
        elif has_motion and not confirmed:
            logger.debug(
                f"👁️ [motion] Detectado pero NO confirmado: "
                f"{self._motion_frames_count}/{self.min_consecutive_frames} frames, "
                f"{len(rects)} rects"
            )

        return confirmed, rects if confirmed else [], mask

    def _detect_adaptive(self, gray, scale, original_shape):
        """Combina MOG2 + KNN + frame_diff"""
        h_mog2, r_mog2, mask_mog2 = self._detect_mog2(gray, scale, original_shape)
        h_knn, r_knn, mask_knn = self._detect_knn(gray, scale, original_shape)
        h_diff, r_diff, mask_diff = self._detect_frame_diff(gray, scale, original_shape)

        votes = sum([h_mog2, h_knn, h_diff])

        if hasattr(self, '_adaptive_counter'):
            self._adaptive_counter += 1
        else:
            self._adaptive_counter = 0
        if self._adaptive_counter % 30 == 0:
            logger.debug(
                f"🔍 [adaptive] Votos: MOG2={h_mog2}, KNN={h_knn}, "
                f"DIFF={h_diff}, total={votes}/3"
            )

        if votes >= 2:
            all_rects = r_mog2 + r_knn + r_diff
            merged = self._merge_rects(all_rects)
            mask = None
            for m in [mask_mog2, mask_knn, mask_diff]:
                if m is not None:
                    mask = m if mask is None else cv2.bitwise_or(mask, m)
            return True, merged, mask

        return False, [], mask_mog2

    def _detect_frame_diff(self, gray, scale, original_shape):
        if self.previous_gray is None:
            self.previous_gray = gray
            return False, [], None

        frame_delta = cv2.absdiff(self.previous_gray, gray)
        frame_delta = cv2.GaussianBlur(frame_delta, (5, 5), 0)
        thresh = cv2.threshold(
            frame_delta, self.sensitivity, 255, cv2.THRESH_BINARY
        )[1]

        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, self.kernel_rect)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, self.kernel_ellipse)
        thresh = cv2.dilate(thresh, self.kernel_ellipse, iterations=self.dilate_iterations)

        self.previous_gray = gray
        return self._extract_motion_rects(thresh, scale, original_shape)

    def _detect_mog2(self, gray, scale, original_shape):
        fg_mask = self.bg_subtractor_mog2.apply(gray, learningRate=self.learning_rate)

        if self.use_shadow_removal:
            _, fg_mask = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)

        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, self.kernel_rect)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, self.kernel_ellipse)
        fg_mask = cv2.dilate(fg_mask, self.kernel_ellipse, iterations=2)

        return self._extract_motion_rects(fg_mask, scale, original_shape)

    def _detect_knn(self, gray, scale, original_shape):
        fg_mask = self.bg_subtractor_knn.apply(gray, learningRate=self.learning_rate)

        if self.use_shadow_removal:
            _, fg_mask = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)

        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, self.kernel_rect)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, self.kernel_ellipse)
        fg_mask = cv2.dilate(fg_mask, self.kernel_ellipse, iterations=2)

        return self._extract_motion_rects(fg_mask, scale, original_shape)

    def _extract_motion_rects(self, mask, scale, original_shape):
        contours, _ = cv2.findContours(
            mask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        rects = []
        inv_scale = 1.0 / scale if scale != 1.0 else 1.0
        min_area_scaled = self.min_area * (scale ** 2)

        filtered = {"small": 0, "density": 0, "aspect": 0, "too_big": 0}

        for contour in contours:
            area = cv2.contourArea(contour)
            if area < min_area_scaled:
                filtered["small"] += 1
                continue

            x, y, w, h = cv2.boundingRect(contour)
            bbox_area = w * h
            density = area / bbox_area if bbox_area > 0 else 0

            if self.use_shape_filter and density < self.min_density:
                filtered["density"] += 1
                continue

            aspect_ratio = max(w, h) / max(min(w, h), 1)
            if aspect_ratio > self.max_aspect_ratio:
                filtered["aspect"] += 1
                continue

            if area > original_shape[0] * original_shape[1] * self.max_area_ratio:
                filtered["too_big"] += 1
                continue

            rects.append((
                int(x * inv_scale), int(y * inv_scale),
                int(w * inv_scale), int(h * inv_scale)
            ))

        if any(filtered.values()):
            logger.debug(
                f"🔍 [motion] {len(contours)} contornos → {len(rects)} rects. "
                f"Filtrados: {filtered}"
            )

        return len(rects) > 0, rects, mask

    def _merge_rects(self, rects):
        if not rects:
            return []
        rects = sorted(rects, key=lambda r: r[2] * r[3], reverse=True)
        merged = []

        while rects:
            x1, y1, w1, h1 = rects.pop(0)
            overlapping = []
            for i, (x2, y2, w2, h2) in enumerate(rects):
                xa, ya = max(x1, x2), max(y1, y2)
                xb, yb = min(x1 + w1, x2 + w2), min(y1 + h1, y2 + h2)
                inter = max(0, xb - xa) * max(0, yb - ya)
                union = w1 * h1 + w2 * h2 - inter
                if union > 0 and inter / union > self.iou_threshold:
                    overlapping.append(i)

            for i in reversed(overlapping):
                ox, oy, ow, oh = rects.pop(i)
                nx1, ny1 = min(x1, ox), min(y1, oy)
                nx2, ny2 = max(x1 + w1, ox + ow), max(y1 + h1, oy + oh)
                x1, y1, w1, h1 = nx1, ny1, nx2 - nx1, ny2 - ny1
            merged.append((x1, y1, w1, h1))

        return merged

    def can_notify(self) -> bool:
        now = time.time()
        if now - self._last_detection_time >= self.cooldown_seconds:
            self._last_detection_time = now
            return True
        remaining = self.cooldown_seconds - (now - self._last_detection_time)
        logger.debug(
            f"⏱️ [motion] Cooldown activo: {remaining:.1f}s restantes"
        )
        return False

    def reset(self):
        self._create_bg_subtractors()
        self.previous_gray = None
        self._motion_frames_count = 0
        self._no_motion_frames_count = 0
        self._last_reinit_time = time.time()
        self.total_detections = 0
        self.motion_intensity = 0.0
        logger.debug("🔄 [motion] Reset completo")

    def draw_motion_rects(self, frame: np.ndarray, rects: List = None) -> np.ndarray:
        result = frame.copy()
        if rects is None:
            rects = self.last_motion_rects

        for (x, y, w, h) in rects:
            intensity = self.motion_intensity
            color = (
                int(50 * (1 - intensity)),
                int(255 * intensity),
                int(255 * (1 - intensity))
            )
            cv2.rectangle(result, (x, y), (x + w, y + h), color, 3)
            label = f"MOV {intensity*100:.0f}%"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(result, (x, y - th - 10), (x + tw + 10, y), color, -1)
            cv2.putText(result, label, (x + 5, y - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        return result