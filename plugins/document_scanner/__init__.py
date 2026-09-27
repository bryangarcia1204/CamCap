"""
Plugin de escaneo de documentos.

Incluye:
- DocumentDetector (detección de bordes + corrección de perspectiva)
- OCRRecognizer (Tesseract OCR)
- ScanManager (orquestador del pipeline)

Depende de: image_enhancer
"""
from .document_detector import DocumentDetector
from .ocr_recognizer import OCRRecognizer
from .scan_manager import ScanManager
from .plugin import DocumentScannerPlugin

__all__ = [
    "DocumentDetector",
    "OCRRecognizer",
    "ScanManager",
    "DocumentScannerPlugin",
]