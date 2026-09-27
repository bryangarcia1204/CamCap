"""
Plugin de detección de movimiento.

Re-exporta las clases principales para compatibilidad.
"""
from .motion_detector import MotionDetector
from .plugin import MotionDetectorPlugin

__all__ = [
    "MotionDetector",
    "MotionDetectorPlugin",
]