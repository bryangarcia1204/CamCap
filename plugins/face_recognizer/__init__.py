"""
Plugin de reconocimiento facial.

Re-exporta las clases principales para compatibilidad.
"""
from .face_recognizer import FaceRecognizer
from .plugin import FaceRecognizerPlugin

__all__ = [
    "FaceRecognizer",
    "FaceRecognizerPlugin",
]