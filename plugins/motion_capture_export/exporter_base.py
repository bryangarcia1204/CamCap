"""
Clase base para todos los exporters.

Define la firma común que el plugin espera:
    export(results, output_path, video_path="", fps=30.0) -> bool
"""
from abc import ABC, abstractmethod
from typing import List

from plugins.motion_capture_export.pose_tracker import FrameResult


class BaseExporter(ABC):
    """Interfaz común para todos los exporters."""

    # Nombre del formato (para mostrar en la UI)
    FORMAT_NAME: str = "base"
    FILE_EXTENSION: str = ""

    @abstractmethod
    def export(
        self,
        results: List[FrameResult],
        output_path: str,
        video_path: str = "",
        fps: float = 30.0,
    ) -> bool:
        """
        Exporta los resultados al formato correspondiente.

        Args:
            results: Lista de FrameResult del tracker.
            output_path: Ruta del archivo de salida.
            video_path: Ruta del video original (opcional, para metadatos).
            fps: FPS del video original.

        Returns:
            True si se exportó correctamente.
        """
        ...