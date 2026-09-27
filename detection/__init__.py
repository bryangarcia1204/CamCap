"""
Módulo de detección - Motion, Face, Document, OCR, Enhancement
"""
from .motion_detector import MotionDetector
from .face_recognizer import FaceRecognizer
from .document_detector import DocumentDetector
from .image_enhancer import ImageEnhancer
from .ocr_recognizer import OCRRecognizer
from .scan_manager import ScanManager

__all__ = [
    'MotionDetector',
    'FaceRecognizer',
    'DocumentDetector',
    'ImageEnhancer',
    'OCRRecognizer',
    'ScanManager',
]