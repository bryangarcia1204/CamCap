"""
Reconocimiento de texto con Tesseract OCR
"""
import cv2
import numpy as np
import os
from typing import Optional, Dict, List
from pathlib import Path
from utils.logger import get_logger

logger = get_logger("OCRRecognizer")


class OCRRecognizer:
    """Reconocimiento de texto usando Tesseract"""

    def __init__(self,
                 lang: str = "spa+eng",
                 tesseract_path: str = None,
                 psm: int = 6,
                 oem: int = 3):
        self.lang = lang
        self.psm = psm
        self.oem = oem
        self._available = False
        self._tesseract = None

        try:
            import pytesseract

            if tesseract_path:
                pytesseract.pytesseract.tesseract_cmd = tesseract_path
            elif os.name == 'nt':
                common_paths = [
                    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                ]
                for path in common_paths:
                    if os.path.exists(path):
                        pytesseract.pytesseract.tesseract_cmd = path
                        break

            self._tesseract = pytesseract
            self._available = True
            print(f"✅ Tesseract OCR disponible (idiomas: {lang})")

        except ImportError:
            print("⚠️ pytesseract no instalado")
            print("   Instala con: pip install pytesseract")

        self.last_text = ""
        self.last_confidence = 0.0
        self.last_data = None

    def recognize(self, image: np.ndarray,
                  preprocess: bool = True) -> str:
        """Extrae texto de una imagen"""
        if not self._available:
            return ""

        if image is None or image.size == 0:
            return ""

        if preprocess:
            # ✅ Import desde el plugin image_enhancer
            from plugins.image_enhancer.image_enhancer import ImageEnhancer
            image = ImageEnhancer.enhance(image, mode="auto")

        if len(image.shape) == 3:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        config = f"--oem {self.oem} --psm {self.psm}"

        try:
            text = self._tesseract.image_to_string(
                image,
                lang=self.lang,
                config=config
            )

            self.last_text = text.strip()

            data = self._tesseract.image_to_data(
                image,
                lang=self.lang,
                config=config,
                output_type=self._tesseract.Output.DICT
            )

            self.last_data = data

            confidences = [int(c) for c in data['conf'] if int(c) > 0]
            if confidences:
                self.last_confidence = sum(confidences) / len(confidences) / 100

            return self.last_text

        except Exception as e:
            print(f"❌ Error en OCR: {e}")
            return ""

    def recognize_with_details(self, image: np.ndarray) -> Dict:
        """Reconoce texto y retorna detalles"""
        text = self.recognize(image)

        if not self._available or self.last_data is None:
            return {"text": text, "confidence": 0, "words": [], "lines": []}

        data = self.last_data
        words = []

        n_boxes = len(data['text'])
        for i in range(n_boxes):
            if int(data['conf'][i]) > 0 and data['text'][i].strip():
                words.append({
                    'text': data['text'][i],
                    'confidence': int(data['conf'][i]) / 100,
                    'left': data['left'][i],
                    'top': data['top'][i],
                    'width': data['width'][i],
                    'height': data['height'][i]
                })

        lines = text.split('\n')
        lines = [line.strip() for line in lines if line.strip()]

        return {
            "text": text,
            "confidence": self.last_confidence,
            "words": words,
            "lines": lines
        }

    def save_text(self, text: str, output_path: str) -> bool:
        """Guarda el texto reconocido en un archivo"""
        try:
            directory = os.path.dirname(output_path)
            if directory:
                os.makedirs(directory, exist_ok=True)

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(text)

            return True
        except Exception as e:
            print(f"❌ Error guardando texto: {e}")
            return False

    def is_available(self) -> bool:
        return self._available

    def reload_config(self):
        """Recarga la config del OCR"""
        from core.settings_manager import settings_manager
        scan = settings_manager.get_scan_settings()

        new_lang = scan.get("language", "spa+eng")
        new_path = scan.get("tesseract_path", "")

        if new_lang != self.lang or new_path:
            self.lang = new_lang

            if new_path:
                try:
                    import pytesseract
                    pytesseract.pytesseract.tesseract_cmd = new_path
                    self._tesseract = pytesseract
                    logger.info(f"🔧 Tesseract path actualizado: {new_path}")
                except Exception as e:
                    logger.error(f"Error actualizando tesseract path: {e}")

            logger.info(f"🔄 OCRRecognizer recargado: lang={self.lang}")

        return True