"""
Plugin: Motion Capture Export.

Procesa fragmentos de video para extraer animaciones de movimiento
usando un pipeline híbrido: YOLOv8-Pose (detección) + MediaPipe Pose
(landmarks detallados).

Modos:
- Video File: procesa un fragmento de video y exporta JSON/CSV/BVH.
- Camera Live: (Fase 3) procesa en tiempo real desde cámaras.

El plugin NO conoce el Core internamente. Se engancha vía eventos
y extensiones genéricas.
"""
from .plugin import MotionCaptureExportPlugin

__all__ = ["MotionCaptureExportPlugin"]