"""
Exportadores de datos de captura de movimiento.

Formatos:
  - JSON: estructura completa con landmarks por frame.
  - CSV:  tabla plana, una fila por persona-frame.
  - BVH:  (Fase 2) formato estándar de animación.
"""
import os
import json
from typing import List, Optional
from datetime import datetime

from utils.logger import get_logger
from .exporter_base import BaseExporter
from .pose_tracker import (
    HybridPoseTracker, FrameResult,
)

logger = get_logger("Plugin.Exporters")


# ============================================================
# JSON EXPORTER
# ============================================================

class JSONExporter(BaseExporter):
    FORMAT_NAME = "json"
    FILE_EXTENSION = ".json"
    """
    Exporta los resultados a un JSON estructurado.

    Formato:
        {
          "meta": {fps, total_frames, duration, video_path, ...},
          "landmarks_names": [...33 nombres...],
          "frames": [
            {
              "frame": 0,
              "timestamp": 0.0,
              "persons": [
                {
                  "track_id": 0,
                  "bbox": [x, y, w, h],
                  "confidence": 0.95,
                  "landmarks": [[x, y, z, vis], ...33...]
                }
              ]
            },
            ...
          ]
        }
    """

    def __init__(self, landmarks_names: Optional[List[str]] = None):
        self.landmarks_names = landmarks_names or HybridPoseTracker.LANDMARK_NAMES

    def _clean_landmarks(self, landmarks):
        """
        Limpia landmarks:
        - vis < 0.3 → inválido, marcar como [0,0,0,0]
        - clamp en bordes (x=0, x=1, y=0, y=1) → probablemente inventado
        """
        cleaned = []
        for lm in landmarks:
            x, y, z, vis = lm
            # Landmark con visibilidad muy baja → inválido
            if vis < 0.3:
                cleaned.append([0.0, 0.0, 0.0, 0.0])
                continue
            # Landmark clampeado a los bordes → probablemente inventado
            # (excepto si el sujeto realmente está pegado al borde)
            if (x <= 0.001 or x >= 0.999 or y <= 0.001 or y >= 0.999):
                # Si además tiene vis baja, es inventado
                if vis < 0.7:
                    cleaned.append([0.0, 0.0, 0.0, 0.0])
                    continue
            cleaned.append([float(x), float(y), float(z), float(vis)])
        return cleaned

    def export(
        self,
        results: List[FrameResult],
        output_path: str,
        video_path: str = "",
        fps: float = 30.0,
    ) -> bool:
        try:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

            frames_data = []
            for r in results:
                persons = []
                for p in r.persons:
                    if p.landmarks is None:
                        continue
                    persons.append({
                        "track_id": int(p.track_id),
                        "bbox": [int(v) for v in p.bbox],
                        "confidence": float(p.confidence),
                        "landmarks": self._clean_landmarks(p.landmarks),
                    })
                frames_data.append({
                    "frame": int(r.frame_index),        # ✅ int()
                    "timestamp": float(round(r.timestamp, 4)),  # ✅ float()
                    "persons": persons,
                })

            data = {
                "meta": {
                    "video_path": str(video_path),
                    "video_filename": str(os.path.basename(video_path) if video_path else ""),
                    "fps": float(fps),
                    "total_frames": int(len(results)),
                    "duration_seconds": float(round(len(results) / fps, 3)) if fps > 0 else 0.0,
                    "exported_at": datetime.now().isoformat(),
                    "pipeline": "YOLOv8-Pose + MediaPipe Pose",
                    "landmarks_count": 33,
                },
                "landmarks_names": list(self.landmarks_names),
                "frames": frames_data,       # ✅ AQUÍ va la lista completa
            }

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            size_kb = os.path.getsize(output_path) / 1024
            logger.info(f"✅ JSON exportado: {output_path} ({size_kb:.1f} KB)")
            return True

        except Exception as e:
            logger.error(f"❌ Error exportando JSON: {e}", exc_info=True)
            return False

# ============================================================
# FACTORY
# ============================================================

def get_exporter(format_name: str):
    """Retorna el exporter adecuado según el nombre del formato."""
    fmt = format_name.lower()
    if fmt == "json":
        return JSONExporter()
    elif fmt == "csv":
        from .csv_exporter import CSVExporter
        return CSVExporter()
    elif fmt == "bvh":
        from .bvh_exporter import BVHExporter
        return BVHExporter()
    else:
        logger.warning(f"⚠️ Formato desconocido: {format_name}, usando JSON")
        return JSONExporter()