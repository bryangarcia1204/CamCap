"""
Detector de documentos con corrección de perspectiva
Basado en OpenCV: Canny + findContours + getPerspectiveTransform
"""
import cv2
import numpy as np
from typing import Optional, Tuple, List
from utils.logger import get_logger

logger = get_logger("DocumentDetector")


class DocumentDetector:
    """Detecta documentos en un frame y corrige su perspectiva"""

    def __init__(self,
                 min_area_ratio: float = 0.15,
                 blur_kernel: int = 5,
                 canny_low: int = 75,
                 canny_high: int = 200):
        """
        Args:
            min_area_ratio: Área mínima del documento respecto al frame (0-1)
            blur_kernel: Tamaño del kernel gaussiano
            canny_low: Umbral bajo para Canny
            canny_high: Umbral alto para Canny
        """
        self.min_area_ratio = min_area_ratio
        self.blur_kernel = blur_kernel if blur_kernel % 2 == 1 else blur_kernel + 1
        self.canny_low = canny_low
        self.canny_high = canny_high

        # Último documento detectado
        self.last_corners = None
        self.last_document = None
        self.last_confidence = 0.0

    def detect(self, frame: np.ndarray) -> Tuple[bool, Optional[np.ndarray], float]:
        """
        Detecta un documento en el frame

        Returns:
            (found, corners, confidence)
        """
        if frame is None or frame.size == 0:
            return False, None, 0.0

        height, width = frame.shape[:2]
        max_dim = 800
        if max(width, height) > max_dim:
            scale = max_dim / max(width, height)
            small = cv2.resize(frame, (int(width * scale), int(height * scale)))
        else:
            scale = 1.0
            small = frame

        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (self.blur_kernel, self.blur_kernel), 0)
        edges = cv2.Canny(blurred, self.canny_low, self.canny_high)

        kernel = np.ones((3, 3), np.uint8)
        edges = cv2.dilate(edges, kernel, iterations=1)

        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)

        frame_area = small.shape[0] * small.shape[1]
        min_area = frame_area * self.min_area_ratio

        for contour in contours[:10]:
            area = cv2.contourArea(contour)
            if area < min_area:
                continue

            peri = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.02 * peri, True)

            if len(approx) == 4:
                corners = approx.reshape(4, 2).astype(np.float32)
                if scale != 1.0:
                    corners /= scale

                corners = self._order_corners(corners)

                area_ratio = area / frame_area
                confidence = min(1.0, area_ratio * 3)

                self.last_corners = corners
                self.last_confidence = confidence

                return True, corners, confidence

        return False, None, 0.0

    def _order_corners(self, corners: np.ndarray) -> np.ndarray:
        """Ordena las esquinas: [top-left, top-right, bottom-right, bottom-left]"""
        rect = np.zeros((4, 2), dtype=np.float32)

        s = corners.sum(axis=1)
        diff = np.diff(corners, axis=1)

        rect[0] = corners[np.argmin(s)]
        rect[2] = corners[np.argmax(s)]
        rect[1] = corners[np.argmin(diff)]
        rect[3] = corners[np.argmax(diff)]

        return rect

    def correct_perspective(self, frame: np.ndarray,
                           corners: np.ndarray) -> np.ndarray:
        """Corrige la perspectiva del documento"""
        if corners is None:
            return frame

        (tl, tr, br, bl) = corners

        width_top = np.linalg.norm(tr - tl)
        width_bottom = np.linalg.norm(br - bl)
        max_width = max(int(width_top), int(width_bottom))

        height_left = np.linalg.norm(bl - tl)
        height_right = np.linalg.norm(br - tr)
        max_height = max(int(height_left), int(height_right))

        dst = np.array([
            [0, 0],
            [max_width - 1, 0],
            [max_width - 1, max_height - 1],
            [0, max_height - 1]
        ], dtype=np.float32)

        M = cv2.getPerspectiveTransform(corners, dst)
        corrected = cv2.warpPerspective(frame, M, (max_width, max_height))

        self.last_document = corrected
        return corrected

    def draw_detection(self, frame: np.ndarray,
                       corners: np.ndarray = None) -> np.ndarray:
        """Dibuja el contorno del documento detectado"""
        result = frame.copy()

        if corners is None:
            corners = self.last_corners

        if corners is not None:
            pts = corners.astype(np.int32).reshape((-1, 1, 2))
            cv2.polylines(result, [pts], True, (0, 255, 0), 3)

            for i, corner in enumerate(corners):
                x, y = int(corner[0]), int(corner[1])
                cv2.circle(result, (x, y), 8, (0, 255, 0), -1)
                cv2.putText(result, str(i), (x + 10, y - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        return result

    def reload_config(self):
        """Recarga parámetros desde config."""
        from core.settings_manager import settings_manager
        scan = settings_manager.get_scan_settings()

        self.min_area_ratio = scan.get("min_area_ratio", 0.15)
        self.canny_low = scan.get("canny_low", 75)
        self.canny_high = scan.get("canny_high", 200)

        self.last_corners = None
        self.last_document = None
        self.last_confidence = 0.0

        logger.info(
            f"🔄 DocumentDetector recargado: "
            f"area_ratio={self.min_area_ratio}, "
            f"canny=({self.canny_low}, {self.canny_high})"
        )
        return True