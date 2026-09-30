"""
Gestor completo del pipeline de escaneo de documentos
"""
import cv2
import numpy as np
import os
from datetime import datetime
from typing import Optional, Dict

from .document_detector import DocumentDetector
from .ocr_recognizer import OCRRecognizer
from utils.logger import get_logger

logger = get_logger("ScanManager")


class ScanManager:
    """Gestiona el pipeline completo de escaneo"""

    def __init__(self, tesseract_path: str = None):
        self.detector = DocumentDetector()
        try:
            from ..image_enhancer import ImageEnhancer
            self.enhancer = ImageEnhancer()
        except ImportError:
            self.enhancer = None
            logger.warning("No tienes el plugin de Enriquesimiento de Imagenes")

        self.ocr = OCRRecognizer(tesseract_path=tesseract_path)

        self.last_scan = None
        self.scan_count = 0

    def process_frame(self, frame: np.ndarray,
                     auto_correct: bool = True,
                     enhance_mode: str = "auto") -> Dict:
        """Procesa un frame completo: detecta → mejora → OCR"""
        result = {
            "document_found": False,
            "confidence": 0.0,
            "corners": None,
            "corrected_image": None,
            "enhanced_image": None,
            "text": "",
            "ocr_confidence": 0.0
        }

        if frame is None or frame.size == 0:
            return result

        # 1. Detectar documento
        found, corners, confidence = self.detector.detect(frame)
        result["document_found"] = found
        result["confidence"] = confidence
        result["corners"] = corners

        if found and auto_correct:
            # 2. Corregir perspectiva
            corrected = self.detector.correct_perspective(frame, corners)
            result["corrected_image"] = corrected

            # 3. Mejorar imagen
            if self.enhancer:
                enhanced = self.enhancer.auto_enhance(corrected)
                result["enhanced_image"] = enhanced

            # 4. OCR
            text = self.ocr.recognize(enhanced, preprocess=False)
            result["text"] = text
            result["ocr_confidence"] = self.ocr.last_confidence
        else:
            # Sin detección: usar frame completo
            if self.enhancer:
                enhanced = self.enhancer.auto_enhance(corrected)
                result["enhanced_image"] = enhanced

            text = self.ocr.recognize(enhanced, preprocess=False)
            result["text"] = text
            result["ocr_confidence"] = self.ocr.last_confidence

        self.last_scan = result
        if result["text"]:
            self.scan_count += 1

        return result

    def scan_and_save(self, frame: np.ndarray,
                     output_dir: str,
                     save_original: bool = False,
                     save_corrected: bool = True,
                     save_text: bool = False) -> Dict:
        """Escanea un frame y guarda los resultados"""
        result = self.process_frame(frame)

        if not result["document_found"] and not result["text"]:
            return {"success": False, "error": "No se detectó documento ni texto"}

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs(output_dir, exist_ok=True)

        saved_files = {}

        try:
            if save_original:
                original_path = os.path.join(output_dir, f"scan_{timestamp}_original.jpg")
                detected = self.detector.draw_detection(frame, result["corners"])
                self._save_image(detected, original_path)
                saved_files["original"] = original_path

            if save_corrected and result["corrected_image"] is not None:
                corrected_path = os.path.join(output_dir, f"scan_{timestamp}_corrected.jpg")
                self._save_image(result["corrected_image"], corrected_path)
                saved_files["corrected"] = corrected_path

            if result["enhanced_image"] is not None:
                enhanced_path = os.path.join(output_dir, f"scan_{timestamp}_enhanced.jpg")
                self._save_image(result["enhanced_image"], enhanced_path)
                saved_files["enhanced"] = enhanced_path

            if save_text and result["text"]:
                text_path = os.path.join(output_dir, f"scan_{timestamp}.txt")
                self.ocr.save_text(result["text"], text_path)
                saved_files["text"] = text_path

        except Exception as e:
            print(f"❌ Error guardando: {e}")
            return {"success": False, "error": str(e)}

        saved_files["success"] = True
        saved_files["text_content"] = result["text"]
        saved_files["ocr_confidence"] = result["ocr_confidence"]

        return saved_files

    def _save_image(self, image: np.ndarray, path: str):
        """Guarda imagen con soporte Unicode"""
        ext = os.path.splitext(path)[1]
        success, buffer = cv2.imencode(ext, image,
                                       [cv2.IMWRITE_JPEG_QUALITY, 92])
        if success:
            with open(path, 'wb') as f:
                f.write(buffer.tobytes())

    def reload_config(self):
        """Recarga TODOS los sub-módulos"""
        logger.info("🔄 Recargando ScanManager completo...")
        try:
            from utils.config_loader import advanced_config
            advanced_config.reload()

            if self.detector and hasattr(self.detector, 'reload_config'):
                self.detector.reload_config()

            if self.enhancer and hasattr(self.enhancer, 'reload_config'):
                self.enhancer.reload_config()

            if self.ocr and hasattr(self.ocr, 'reload_config'):
                self.ocr.reload_config()

            self.last_scan = None
            logger.info("✅ ScanManager recargado")
            return True
        except Exception as e:
            logger.error(f"❌ Error recargando ScanManager: {e}", exc_info=True)
            return False