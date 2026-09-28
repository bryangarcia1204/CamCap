"""
Exportadores de datos de captura de movimiento.

Formatos:
  - JSON: estructura completa con landmarks por frame.
  - CSV:  tabla plana, una fila por persona-frame.
  - BVH:  (Fase 2) formato estándar de animación.
"""
import os
import json
import csv
import time
from typing import List, Optional
from datetime import datetime

from utils.logger import get_logger
from plugins.motion_capture_export.pose_tracker import (
    HybridPoseTracker, FrameResult,
)

logger = get_logger("Plugin.Exporters")


# ============================================================
# JSON EXPORTER
# ============================================================

class JSONExporter:
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
                        "track_id": p.track_id,
                        "bbox": list(p.bbox),
                        "confidence": round(p.confidence, 4),
                        "landmarks": [
                            [round(v, 6) for v in lm]
                            for lm in p.landmarks
                        ],
                    })
                frames_data.append({
                    "frame": r.frame_index,
                    "timestamp": round(r.timestamp, 4),
                    "persons": persons,
                })

            data = {
                "meta": {
                    "video_path": video_path,
                    "video_filename": os.path.basename(video_path) if video_path else "",
                    "fps": fps,
                    "total_frames": len(results),
                    "duration_seconds": round(len(results) / fps, 3) if fps > 0 else 0,
                    "exported_at": datetime.now().isoformat(),
                    "pipeline": "YOLOv8-Pose + MediaPipe Pose",
                    "landmarks_count": 33,
                },
                "landmarks_names": self.landmarks_names,
                "frames": frames_data,
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
# CSV EXPORTER
# ============================================================

class CSVExporter:
    """
    Exporta los resultados a un CSV plano.

    Una fila por persona por frame. Columnas:
        frame, timestamp, track_id, confidence, bbox_x, bbox_y, bbox_w, bbox_h,
        nose_x, nose_y, nose_z, nose_vis,
        left_shoulder_x, ... (33 landmarks x 4)
    """

    def __init__(self, landmarks_names: Optional[List[str]] = None):
        self.landmarks_names = landmarks_names or HybridPoseTracker.LANDMARK_NAMES

    def export(
        self,
        results: List[FrameResult],
        output_path: str,
    ) -> bool:
        try:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

            # Construir header
            header = ["frame", "timestamp", "track_id", "confidence",
                      "bbox_x", "bbox_y", "bbox_w", "bbox_h"]
            for name in self.landmarks_names:
                header.extend([
                    f"{name}_x", f"{name}_y", f"{name}_z", f"{name}_vis"
                ])

            with open(output_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(header)

                for r in results:
                    for p in r.persons:
                        if p.landmarks is None:
                            continue
                        row = [
                            r.frame_index,
                            round(r.timestamp, 4),
                            p.track_id,
                            round(p.confidence, 4),
                            p.bbox[0], p.bbox[1], p.bbox[2], p.bbox[3],
                        ]
                        for lm in p.landmarks:
                            row.extend([round(v, 6) for v in lm])
                        writer.writerow(row)

            size_kb = os.path.getsize(output_path) / 1024
            logger.info(f"✅ CSV exportado: {output_path} ({size_kb:.1f} KB)")
            return True

        except Exception as e:
            logger.error(f"❌ Error exportando CSV: {e}", exc_info=True)
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
        return CSVExporter()
    else:
        logger.warning(f"⚠️ Formato desconocido: {format_name}, usando JSON")
        return JSONExporter()