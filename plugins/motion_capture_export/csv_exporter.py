"""
Exportador CSV mejorado.

Formato:
  - Cabecera con metadatos (comentarios con '#')
  - Una fila por persona por frame
  - Los frames sin persona se marcan con track_id=-1
  - Columnas: frame, timestamp, track_id, confidence, bbox_x/y/w/h,
    y para cada landmark: <name>_x, <name>_y, <name>_z, <name>_vis
"""
import os
import csv
from datetime import datetime
from typing import List, Optional

from utils.logger import get_logger
from .pose_tracker import (
    HybridPoseTracker, FrameResult,
)

logger = get_logger("Plugin.CSVExporter")


class CSVExporter:
    """
    Exporta los resultados a un CSV plano.

    Incluye metadatos en comentarios (#) al principio, que pandas
    puede saltarse con `comment='#'`.
    """

    def __init__(self, landmarks_names: Optional[List[str]] = None):
        self.landmarks_names = landmarks_names or HybridPoseTracker.LANDMARK_NAMES

    # ==================== API ====================

    def export(
        self,
        results: List[FrameResult],
        output_path: str,
        video_path: str = "",
        fps: float = 30.0,
    ) -> bool:
        """
        Exporta los resultados a CSV.

        Args:
            results: Lista de FrameResult del tracker.
            output_path: Ruta del archivo .csv.
            video_path: Ruta del video original (para metadatos).
            fps: FPS del video.

        Returns:
            True si se exportó correctamente.
        """
        try:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

            # === Contadores ===
            total_frames = len(results)
            frames_with_persons = sum(
                1 for r in results if r.persons
            )
            total_detections = sum(len(r.persons) for r in results)

            with open(output_path, "w", newline="", encoding="utf-8") as f:
                # === METADATOS como comentarios ===
                f.write(f"# video_path: {video_path}\n")
                f.write(f"# video_filename: "
                        f"{os.path.basename(video_path) if video_path else ''}\n")
                f.write(f"# fps: {fps}\n")
                f.write(f"# total_frames: {total_frames}\n")
                f.write(f"# frames_with_persons: {frames_with_persons}\n")
                f.write(f"# total_detections: {total_detections}\n")
                f.write(f"# exported_at: {datetime.now().isoformat()}\n")
                f.write(f"# pipeline: YOLOv8-Pose + MediaPipe Pose\n")
                f.write(f"# landmarks_count: 33\n")
                f.write("#\n")

                # === HEADER ===
                writer = csv.writer(f)
                header = [
                    "frame", "timestamp", "track_id", "confidence",
                    "bbox_x", "bbox_y", "bbox_w", "bbox_h",
                ]
                for name in self.landmarks_names:
                    header.extend([
                        f"{name}_x",
                        f"{name}_y",
                        f"{name}_z",
                        f"{name}_vis",
                    ])
                writer.writerow(header)

                # === DATOS ===
                frames_written = 0
                for r in results:
                    if not r.persons:
                        # Fila "vacía" para frames sin detección
                        writer.writerow(self._empty_row(r))
                        frames_written += 1
                        continue

                    for p in r.persons:
                        writer.writerow(self._person_row(r, p))
                        frames_written += 1

            size_kb = os.path.getsize(output_path) / 1024
            logger.info(
                f"✅ CSV exportado: {output_path} "
                f"({size_kb:.1f} KB, {frames_written} filas)"
            )
            return True

        except Exception as e:
            logger.error(f"❌ Error exportando CSV: {e}", exc_info=True)
            return False

    # ==================== HELPERS ====================

    def _person_row(self, frame: FrameResult, person) -> list:
        """Construye una fila para una persona en un frame."""
        row = [
            int(frame.frame_index),
            float(round(frame.timestamp, 4)),
            int(person.track_id),
            float(round(person.confidence, 4)),
            int(person.bbox[0]),
            int(person.bbox[1]),
            int(person.bbox[2]),
            int(person.bbox[3]),
        ]

        # Landmarks (con filtrado de vis baja)
        for lm in (person.landmarks or []):
            x, y, z, vis = float(lm[0]), float(lm[1]), float(lm[2]), float(lm[3])

            # Filtrar landmarks con vis muy baja
            if vis < 0.3:
                row.extend([0.0, 0.0, 0.0, 0.0])
            else:
                row.extend([
                    round(x, 6),
                    round(y, 6),
                    round(z, 6),
                    round(vis, 6),
                ])

        # Rellenar si faltan landmarks
        expected_values = 33 * 4
        current_landmark_values = len(row) - 8
        if current_landmark_values < expected_values:
            row.extend([0.0] * (expected_values - current_landmark_values))

        return row

    def _empty_row(self, frame: FrameResult) -> list:
        """Construye una fila vacía (sin personas) para un frame."""
        row = [
            int(frame.frame_index),
            float(round(frame.timestamp, 4)),
            -1,      # track_id = -1 indica "sin persona"
            0.0,     # confidence
            0, 0, 0, 0,   # bbox vacía
        ]
        # 33 landmarks × 4 valores = 132 ceros
        row.extend([0.0] * (33 * 4))
        return row