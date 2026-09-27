"""
DEPRECATED: movido a plugins/document_scanner/.
"""
import warnings
warnings.warn(
    "detection.ocr_recognizer está deprecado. "
    "Usa plugins.document_scanner.ocr_recognizer en su lugar.",
    DeprecationWarning, stacklevel=2,
)
from plugins.document_scanner.ocr_recognizer import OCRRecognizer
__all__ = ["OCRRecognizer"]