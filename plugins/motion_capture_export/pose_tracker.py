"""
PoseTracker Híbrido: YOLOv8-Pose + MediaPipe Pose.

Arquitectura:
  1. YOLOv8n-Pose detecta bounding boxes de todas las personas en el frame.
  2. Por cada bbox, se hace un crop y se corre MediaPipe Pose.
  3. Se obtienen 33 landmarks detallados por persona.
  4. Un tracker IoU mantiene la identidad entre frames.

Por qué híbrido:
  - YOLO es rápido y detecta múltiples personas en una pasada (16 FPS en CPU).
  - MediaPipe da 33 landmarks detallados (incluye manos, pies, cara).
  - YOLO solo da 17 keypoints sin detalle de manos.
  - Combinado: lo mejor de ambos mundos.

Referencias:
  - YOLOv8-Pose: Ultralytics, 17 keypoints COCO, ONNX exportable.
  - MediaPipe Pose: 33 landmarks, pseudo-3D, ligero en CPU.
"""
import os
import time
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

from utils.logger import get_logger

logger = get_logger("Plugin.PoseTracker")


# ============================================================
# DATA CLASSES
# ============================================================

@dataclass
class PersonDetection:
    """Una persona detectada por YOLO."""
    bbox: Tuple[int, int, int, int]     # (x, y, w, h)
    confidence: float
    track_id: int = -1
    landmarks: Optional[List[List[float]]] = None  # 33 x (x, y, z, visibility)


@dataclass
class FrameResult:
    """Resultado de un frame procesado."""
    frame_index: int
    timestamp: float
    persons: List[PersonDetection] = field(default_factory=list)


# ============================================================
# TRACKER IOU SIMPLE
# ============================================================

class IoUTracker:
    """
    Tracker simple basado en IoU.

    Mantiene la identidad de personas entre frames asignando un
    track_id persistente a cada bbox que se solape con el frame anterior.
    """

    def __init__(self, iou_threshold: float = 0.3, max_lost: int = 5):
        self.iou_threshold = iou_threshold
        self.max_lost = max_lost
        self._next_id = 0
        self._tracks: Dict[int, dict] = {}   # track_id → {bbox, lost}

    def update(self, detections: List[PersonDetection]) -> List[PersonDetection]:
        """Asigna track_id a cada detección."""
        # Marcar todos como perdidos
        for tid in self._tracks:
            self._tracks[tid]["lost"] += 1

        used = set()

        for det in detections:
            best_tid = -1
            best_iou = self.iou_threshold

            for tid, track in self._tracks.items():
                if tid in used:
                    continue
                iou = self._iou(det.bbox, track["bbox"])
                if iou > best_iou:
                    best_iou = iou
                    best_tid = tid

            if best_tid >= 0:
                det.track_id = best_tid
                self._tracks[best_tid] = {"bbox": det.bbox, "lost": 0}
                used.add(best_tid)
            else:
                det.track_id = self._next_id
                self._tracks[self._next_id] = {"bbox": det.bbox, "lost": 0}
                self._next_id += 1

        # Eliminar tracks perdidos
        for tid in list(self._tracks.keys()):
            if self._tracks[tid]["lost"] > self.max_lost:
                del self._tracks[tid]

        return detections

    @staticmethod
    def _iou(a: Tuple, b: Tuple) -> float:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        x1, y1 = max(ax, bx), max(ay, by)
        x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        union = aw * ah + bw * bh - inter
        return inter / union if union > 0 else 0.0


# ============================================================
# POSE TRACKER HÍBRIDO
# ============================================================

class HybridPoseTracker:
    """
    Pipeline híbrido YOLOv8-Pose + MediaPipe Pose.

    Uso:
        tracker = HybridPoseTracker()
        tracker.load()
        result = tracker.process_frame(frame_bgr, frame_index, timestamp)
        for person in result.persons:
            print(person.track_id, person.landmarks)
        tracker.release()
    """

    # MediaPipe Pose landmark names (33 puntos)
    LANDMARK_NAMES = [
        "nose", "left_eye_inner", "left_eye", "left_eye_outer",
        "right_eye_inner", "right_eye", "right_eye_outer",
        "left_ear", "right_ear", "mouth_left", "mouth_right",
        "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
        "left_wrist", "right_wrist", "left_pinky", "right_pinky",
        "left_index", "right_index", "left_thumb", "right_thumb",
        "left_hip", "right_hip", "left_knee", "right_knee",
        "left_ankle", "right_ankle", "left_heel", "right_heel",
        "left_foot_index", "right_foot_index",
    ]

    def __init__(
        self,
        yolo_model: str = "plugins/motion_capture_export/models/yolov8n-pose.pt",
        yolo_conf: float = 0.4,
        mp_complexity: int = 1,
        mp_detection_conf: float = 0.5,
        mp_tracking_conf: float = 0.5,
        iou_threshold: float = 0.3,
        min_bbox_size: int = 40,
        pad_ratio: float = 0.15,
    ):
        """
        Args:
            yolo_model: nombre del modelo YOLO ('yolov8n-pose.pt' es el más ligero)
            yolo_conf: confianza mínima de detección de persona
            mp_complexity: 0=lite, 1=full, 2=heavy (solo 0/1 en versión nueva)
            mp_detection_conf: confianza mínima MediaPipe
            mp_tracking_conf: confianza de tracking MediaPipe
            iou_threshold: umbral IoU para asociar bbox entre frames
            min_bbox_size: bbox mínimo para correr MediaPipe
            pad_ratio: padding alrededor del bbox antes del crop
        """
        self.yolo_model_name = yolo_model
        self.yolo_conf = yolo_conf
        self.mp_complexity = mp_complexity
        self.mp_detection_conf = mp_detection_conf
        self.mp_tracking_conf = mp_tracking_conf
        self.min_bbox_size = min_bbox_size
        self.pad_ratio = pad_ratio

        self._yolo = None
        self._mp_pose = None
        self._tracker = IoUTracker(iou_threshold=iou_threshold)
        self._loaded = False

        logger.debug(
            f"🔧 [init] HybridPoseTracker: yolo={yolo_model}, "
            f"mp_complexity={mp_complexity}, conf={yolo_conf}"
        )

    # ==================== CARGA ====================

    def load(self) -> bool:
        """Carga los modelos YOLO y MediaPipe Tasks."""
        try:
            # 1. Cargar YOLO (igual que antes)
            from ultralytics import YOLO
            self._yolo = YOLO(self.yolo_model_name)
            logger.info(f"✅ YOLO cargado: {self.yolo_model_name}")

            # 2. Cargar MediaPipe Tasks
            # Ruta al modelo .task que descargaste
            model_path = os.path.join(os.path.dirname(__file__), "models", "pose_landmarker_lite.task")
            
            # Si no existe el modelo, avisar
            if not os.path.exists(model_path):
                logger.error(f"❌ Modelo MediaPipe .task no encontrado en: {model_path}")
                logger.error("Descárgalo con: curl -L -o models/pose_landmarker_lite.task <URL>")
                return False

            # Configurar opciones de la Tasks API
            base_options = python.BaseOptions(model_asset_path=model_path)
            options = vision.PoseLandmarkerOptions(
                base_options=base_options,
                running_mode=vision.RunningMode.IMAGE,  # Usamos modo IMAGE para análisis batch
                num_poses=1,  # Ajusta si necesitas detectar más personas por crop
                min_pose_detection_confidence=self.mp_detection_conf,
                min_pose_presence_confidence=0.5,
                min_tracking_confidence=self.mp_tracking_conf,
                output_segmentation_masks=False,
            )
            
            # Crear el landmarker
            self._mp_pose = vision.PoseLandmarker.create_from_options(options)
            logger.info(f"✅ MediaPipe Tasks (PoseLandmarker) cargado")

            self._loaded = True
            return True

        except ImportError as e:
            logger.error(f"❌ Faltan dependencias: {e}\nInstala con: pip install ultralytics mediapipe")
            return False
        except Exception as e:
            logger.error(f"❌ Error cargando modelos: {e}", exc_info=True)
            return False

    def release(self):
        """Libera recursos."""
        try:
            if self._mp_pose is not None:
                self._mp_pose.close()
        except Exception:
            pass
        self._mp_pose = None
        self._yolo = None
        self._loaded = False
        logger.debug("🔌 HybridPoseTracker liberado")

    # ==================== PROCESAMIENTO ====================

    def process_frame(self, frame_bgr: np.ndarray, frame_index: int = 0, timestamp: float = 0.0) -> FrameResult:
        """Procesa un frame con YOLO + MediaPipe Tasks."""
        if not self._loaded:
            return FrameResult(frame_index, timestamp)

        h, w = frame_bgr.shape[:2]

        # 1. YOLO detecta personas (igual que antes)
        detections = self._detect_persons_yolo(frame_bgr)
        if not detections:
            return FrameResult(frame_index, timestamp, [])
        
        detections = self._tracker.update(detections)

        # 2. Por cada persona, correr MediaPipe Tasks en el crop
        import cv2
        
        for det in detections:
            x, y, bw, bh = det.bbox
            if bw < self.min_bbox_size or bh < self.min_bbox_size:
                continue

            # Padding
            pad_w, pad_h = int(bw * self.pad_ratio), int(bh * self.pad_ratio)
            x1 = max(0, x - pad_w)
            y1 = max(0, y - pad_h)
            x2 = min(w, x + bw + pad_w)
            y2 = min(h, y + bh + pad_h)

            # ✅ Forzar crop cuadrado (MediaPipe Tasks se confunde con ROI no cuadrada)
            cw = x2 - x1
            ch = y2 - y1
            side = max(cw, ch)
            cx = x1 + cw // 2
            cy = y1 + ch // 2
            x1 = max(0, cx - side // 2)
            y1 = max(0, cy - side // 2)
            x2 = min(w, x1 + side)
            y2 = min(h, y1 + side)

            crop = frame_bgr[y1:y2, x1:x2]
            if crop.size == 0 or crop.shape[0] < 50 or crop.shape[1] < 50:
                continue

            rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            rgb = np.ascontiguousarray(rgb)

            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            results = self._mp_pose.detect(mp_image)

            if results.pose_landmarks:
                pose_lms = results.pose_landmarks[0]
                landmarks = []
                for lm in pose_lms:
                    x = max(0.0, min(1.0, float(lm.x)))     # clamp
                    y = max(0.0, min(1.0, float(lm.y)))     # clamp
                    z = float(lm.z)                          # z puede ser negativo, no clamp
                    vis = float(lm.visibility)
                    landmarks.append([x, y, z, vis])
                det.landmarks = landmarks

        return FrameResult(frame_index=frame_index, timestamp=timestamp, persons=detections)

    # ==================== YOLO ====================

    def _detect_persons_yolo(self, frame_bgr: np.ndarray) -> List[PersonDetection]:
        """Corre YOLO y devuelve lista de PersonDetection."""
        detections = []
        try:
            results = self._yolo(frame_bgr, verbose=False, conf=self.yolo_conf)

            if not results:
                return detections

            result = results[0]
            if result.boxes is None or len(result.boxes) == 0:
                return detections

            boxes = result.boxes
            # YOLO-pose devuelve boxes con xyxy y keypoints
            for i in range(len(boxes)):
                # Clase 0 = persona
                cls = int(boxes.cls[i].item()) if boxes.cls is not None else 0
                if cls != 0:
                    continue

                conf = float(boxes.conf[i].item()) if boxes.conf is not None else 0.0
                xyxy = boxes.xyxy[i].cpu().numpy()
                x1, y1, x2, y2 = xyxy.astype(int)
                x1 = max(0, x1)
                y1 = max(0, y1)
                x2 = min(frame_bgr.shape[1], x2)
                y2 = min(frame_bgr.shape[0], y2)

                w = x2 - x1
                h = y2 - y1
                if w <= 0 or h <= 0:
                    continue

                detections.append(PersonDetection(
                    bbox=(x1, y1, w, h),
                    confidence=conf,
                ))

        except Exception as e:
            logger.error(f"❌ Error en YOLO: {e}", exc_info=True)

        return detections

    # ==================== UTILIDADES ====================

    @staticmethod
    def landmarks_to_dict(landmarks: List[List[float]]) -> Dict[str, List[float]]:
        """Convierte lista de 33 landmarks a dict con nombres."""
        return {
            HybridPoseTracker.LANDMARK_NAMES[i]: landmarks[i]
            for i in range(min(len(landmarks), 33))
        }

    def get_landmark_names(self) -> List[str]:
        return list(self.LANDMARK_NAMES)