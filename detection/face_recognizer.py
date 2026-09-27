"""
DEPRECATED: Este módulo ha sido movido a `plugins/face_recognizer/`.

Shim de compatibilidad para imports legacy y tests.
"""
import warnings

warnings.warn(
    "detection.face_recognizer está deprecado. "
    "Usa plugins.face_recognizer.face_recognizer en su lugar.",
    DeprecationWarning,
    stacklevel=2,
)

from plugins.face_recognizer.face_recognizer import FaceRecognizer

__all__ = ["FaceRecognizer"]