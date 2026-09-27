"""
Módulo de mejora de imagen - CON ANÁLISIS AVANZADO Y PRESETS
"""
import cv2
import numpy as np
from typing import Dict, Tuple, Optional, List
from utils.logger import get_logger

logger = get_logger("ImageEnhancer")


class ImageEnhancer:
    """Mejora imágenes con análisis de calidad y presets configurables"""

    # ==================== PRESETS ====================

    PRESETS = {
        "auto": {
            "denoise": "auto",
            "sharpen": "auto",
            "brightness": "auto",
            "contrast": "auto",
            "auto_contrast": "auto",
            "exposure_fix": "auto",
            "white_balance": "auto",
            "gamma": "auto",
            "saturation": "auto",
        },
        "documento": {
            "denoise": True,
            "denoise_strength": 8,
            "sharpen": True,
            "sharpen_strength": 1.5,
            "auto_contrast": True,
            "exposure_fix": True,
            "white_balance": True,
            "gamma": 1.1,
            "saturation": 0.9,
            "binarize": False,
        },
        "foto": {
            "denoise": False,
            "sharpen": True,
            "sharpen_strength": 0.8,
            "auto_contrast": True,
            "exposure_fix": True,
            "white_balance": True,
            "gamma": 1.0,
            "saturation": 1.1,
            "vibrance": True,
        },
        "noche": {
            "denoise": True,
            "denoise_strength": 20,
            "sharpen": True,
            "sharpen_strength": 1.8,
            "brightness": 25,
            "contrast": 1.15,
            "auto_contrast": True,
            "exposure_fix": True,
            "white_balance": True,
            "gamma": 0.9,
            "saturation": 1.0,
        },
        "retrato": {
            "denoise": True,
            "denoise_strength": 6,
            "sharpen": True,
            "sharpen_strength": 0.7,
            "auto_contrast": True,
            "exposure_fix": True,
            "white_balance": True,
            "gamma": 1.05,
            "saturation": 1.05,
            "skin_smooth": True,
        },
        "paisaje": {
            "denoise": False,
            "sharpen": True,
            "sharpen_strength": 1.2,
            "auto_contrast": True,
            "exposure_fix": True,
            "white_balance": True,
            "gamma": 1.0,
            "saturation": 1.25,
            "vibrance": True,
            "vignette": -0.15,
        },
        "ninguno": {
            "denoise": False,
            "sharpen": False,
            "auto_contrast": False,
            "exposure_fix": False,
            "white_balance": False,
        },
    }

    # === OPTIMIZACIÓN: CLAHE compartido ===
    _shared_clahe = None

    # === OPTIMIZACIÓN: Cache de LUTs de gamma ===
    _gamma_lut_cache = {}
    _MAX_GAMMA_CACHE = 20

    # === OPTIMIZACIÓN: Cache de kernels de viñeteo ===
    _vignette_cache = {}
    _MAX_VIGNETTE_CACHE = 10

    @classmethod
    def _get_clahe(cls):
        if cls._shared_clahe is None:
            cls._shared_clahe = cv2.createCLAHE(
                clipLimit=2.0, tileGridSize=(8, 8)
            )
        return cls._shared_clahe

    @classmethod
    def _get_gamma_lut(cls, gamma: float) -> np.ndarray:
        """Retorna una LUT cacheada para el valor de gamma"""
        key = round(gamma, 2)
        if key in cls._gamma_lut_cache:
            return cls._gamma_lut_cache[key]

        inv_gamma = 1.0 / gamma
        lut = np.array([
            ((i / 255.0) ** inv_gamma) * 255
            for i in range(256)
        ]).astype(np.uint8)

        if len(cls._gamma_lut_cache) >= cls._MAX_GAMMA_CACHE:
            cls._gamma_lut_cache.clear()

        cls._gamma_lut_cache[key] = lut
        return lut

    # ==================== ANÁLISIS DE CALIDAD ====================

    @staticmethod
    def assess_quality(frame: np.ndarray) -> Dict:
        """Evalúa calidad con métricas adicionales"""
        if frame is None or frame.size == 0:
            return {
                "blur_score": 0, "brightness_score": 0,
                "contrast_score": 0, "noise_score": 0,
                "exposure_score": 0, "white_balance_score": 0,
                "saturation_score": 0, "overall_score": 0,
                "problems": ["Imagen vacía"], "recommendations": []
            }

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame

        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        blur_variance = laplacian.var()
        blur_score = min(1.0, blur_variance / 500)

        brightness = gray.mean()
        brightness_score = 1.0 - abs(brightness - 128) / 128

        contrast = gray.std()
        contrast_score = min(1.0, contrast / 80)

        denoised = cv2.medianBlur(gray, 3)
        noise_estimate = np.abs(
            gray.astype(np.float32) - denoised.astype(np.float32)
        ).mean()
        noise_score = max(0, 1.0 - noise_estimate / 30)

        over = np.sum(gray > 240) / gray.size
        under = np.sum(gray < 15) / gray.size
        exposure_score = max(0, 1.0 - (over + under) * 3)

        white_balance_score = ImageEnhancer._assess_white_balance(frame)
        saturation_score = ImageEnhancer._assess_saturation(frame)

        overall = (
            blur_score * 0.25 +
            brightness_score * 0.15 +
            contrast_score * 0.15 +
            noise_score * 0.10 +
            exposure_score * 0.10 +
            white_balance_score * 0.15 +
            saturation_score * 0.10
        )

        problems = []
        recommendations = []

        if blur_score < 0.3:
            problems.append("Imagen borrosa o movida")
            recommendations.append("Aplicar nitidez fuerte")
        elif blur_score < 0.5:
            problems.append("Nitidez mejorable")
            recommendations.append("Aplicar nitidez suave")

        if brightness_score < 0.4:
            if brightness < 80:
                problems.append("Imagen oscura")
                recommendations.append("Aumentar brillo y gamma")
            else:
                problems.append("Imagen clara")
                recommendations.append("Reducir brillo")

        if contrast_score < 0.3:
            problems.append("Contraste bajo")
            recommendations.append("Aplicar CLAHE")

        if noise_score < 0.4:
            problems.append("Ruido excesivo")
            recommendations.append("Reducir ruido (NLM)")

        if exposure_score < 0.5:
            problems.append("Problemas de exposición")
            recommendations.append("Corregir exposición")

        if white_balance_score < 0.5:
            problems.append("Balance de blancos incorrecto")
            recommendations.append("Aplicar white balance")

        if saturation_score < 0.4:
            problems.append("Colores desaturados")
            recommendations.append("Aumentar saturación/vibrance")

        if not problems:
            problems.append("Buena calidad")

        return {
            "blur_score": round(blur_score, 3),
            "brightness_score": round(brightness_score, 3),
            "contrast_score": round(contrast_score, 3),
            "noise_score": round(noise_score, 3),
            "exposure_score": round(exposure_score, 3),
            "white_balance_score": round(white_balance_score, 3),
            "saturation_score": round(saturation_score, 3),
            "overall_score": round(overall, 3),
            "brightness_value": round(brightness, 1),
            "contrast_value": round(contrast, 1),
            "blur_variance": round(blur_variance, 1),
            "problems": problems,
            "recommendations": recommendations
        }

    @staticmethod
    def _assess_white_balance(frame: np.ndarray) -> float:
        if len(frame.shape) < 3:
            return 1.0
        b, g, r = cv2.split(frame.astype(np.float32))
        mean_b, mean_g, mean_r = b.mean(), g.mean(), r.mean()
        if mean_g < 1:
            return 0.5
        dev = (abs(mean_r - mean_g) + abs(mean_b - mean_g)) / (2 * mean_g)
        return max(0.0, 1.0 - dev * 2)

    @staticmethod
    def _assess_saturation(frame: np.ndarray) -> float:
        if len(frame.shape) < 3:
            return 1.0
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        sat = hsv[:, :, 1].mean() / 255.0
        if 0.3 <= sat <= 0.6:
            return 1.0
        elif sat < 0.3:
            return sat / 0.3
        else:
            return max(0.0, 1.0 - (sat - 0.6) / 0.4)

    # ==================== MEJORA PRINCIPAL ====================

    @staticmethod
    def enhance(frame: np.ndarray,
                denoise: bool = False,
                sharpen: bool = False,
                brightness: int = 0,
                contrast: float = 1.0,
                auto_contrast: bool = False,
                exposure_fix: bool = False,
                sharpen_strength: float = 1.0,
                denoise_strength: int = 10,
                white_balance: bool = False,
                gamma: float = 1.0,
                saturation: float = 1.0,
                vibrance: bool = False,
                skin_smooth: bool = False,
                vignette: float = 0.0,
                binarize: bool = False,
                preset: str = None) -> np.ndarray:
        """Aplica mejoras a la imagen."""
        if frame is None or frame.size == 0:
            return frame

        if preset and preset in ImageEnhancer.PRESETS:
            p = ImageEnhancer.PRESETS[preset]
            if preset == "auto":
                return ImageEnhancer.auto_enhance(frame)
            denoise = p.get("denoise", denoise)
            sharpen = p.get("sharpen", sharpen)
            brightness = p.get("brightness", brightness)
            contrast = p.get("contrast", contrast)
            auto_contrast = p.get("auto_contrast", auto_contrast)
            exposure_fix = p.get("exposure_fix", exposure_fix)
            sharpen_strength = p.get("sharpen_strength", sharpen_strength)
            denoise_strength = p.get("denoise_strength", denoise_strength)
            white_balance = p.get("white_balance", white_balance)
            gamma = p.get("gamma", gamma)
            saturation = p.get("saturation", saturation)
            vibrance = p.get("vibrance", vibrance)
            skin_smooth = p.get("skin_smooth", skin_smooth)
            vignette = p.get("vignette", vignette)
            binarize = p.get("binarize", binarize)

        result = frame.copy()

        if white_balance:
            result = ImageEnhancer._auto_white_balance(result)

        if exposure_fix:
            result = ImageEnhancer._fix_exposure(result)

        if brightness != 0 or contrast != 1.0:
            result = ImageEnhancer._adjust_bc(result, brightness, contrast)

        if gamma != 1.0:
            result = ImageEnhancer._adjust_gamma(result, gamma)

        if auto_contrast:
            result = ImageEnhancer._apply_clahe(result)

        if saturation != 1.0:
            result = ImageEnhancer._adjust_saturation(result, saturation)
        if vibrance:
            result = ImageEnhancer._apply_vibrance(result)

        if denoise:
            try:
                result = cv2.fastNlMeansDenoisingColored(
                    result, None,
                    denoise_strength, denoise_strength,
                    7, 21
                )
            except Exception as e:
                logger.error(f"Error denoising: {e}")

        if skin_smooth:
            result = ImageEnhancer._skin_smooth(result)

        if sharpen:
            result = ImageEnhancer._apply_sharpen(result, sharpen_strength)

        if vignette != 0.0:
            result = ImageEnhancer._apply_vignette(result, vignette)

        if binarize:
            result = ImageEnhancer._binarize_document(result)

        return result

    # ==================== AUTO-ENHANCE ====================

    @staticmethod
    def auto_enhance(frame: np.ndarray) -> np.ndarray:
        """Mejora automática basada en análisis"""
        if frame is None or frame.size == 0:
            return frame

        quality = ImageEnhancer.assess_quality(frame)

        brightness_val = quality["brightness_value"]
        if brightness_val < 80:
            gamma = 0.85
        elif brightness_val > 180:
            gamma = 1.15
        else:
            gamma = 1.0

        return ImageEnhancer.enhance(
            frame,
            denoise=quality["noise_score"] < 0.5,
            sharpen=quality["blur_score"] < 0.6,
            auto_contrast=quality["contrast_score"] < 0.5,
            exposure_fix=quality["exposure_score"] < 0.6,
            white_balance=quality["white_balance_score"] < 0.7,
            gamma=gamma,
            saturation=1.05 if quality["saturation_score"] < 0.5 else 1.0,
            vibrance=quality["saturation_score"] < 0.5,
        )

    # ==================== OPERACIONES INDIVIDUALES ====================

    @staticmethod
    def _adjust_bc(frame: np.ndarray, brightness: int, contrast: float) -> np.ndarray:
        result = frame.astype(np.float32)
        result = (result - 128) * contrast + 128
        result = result + brightness
        return np.clip(result, 0, 255).astype(np.uint8)

    @staticmethod
    def _adjust_gamma(frame: np.ndarray, gamma: float) -> np.ndarray:
        if gamma == 1.0:
            return frame
        table = ImageEnhancer._get_gamma_lut(gamma)
        return cv2.LUT(frame, table)

    @staticmethod
    def _apply_clahe(frame: np.ndarray) -> np.ndarray:
        clahe = ImageEnhancer._get_clahe()

        if len(frame.shape) == 3:
            lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            l = clahe.apply(l)
            lab = cv2.merge([l, a, b])
            return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        else:
            return clahe.apply(frame)

    @staticmethod
    def _apply_sharpen(frame: np.ndarray, strength: float = 1.0) -> np.ndarray:
        blurred = cv2.GaussianBlur(frame, (0, 0), sigmaX=1.5)
        sharpened = cv2.addWeighted(frame, 1.0 + strength, blurred, -strength, 0)
        return sharpened

    @staticmethod
    def _fix_exposure(frame: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
        mean = gray.mean()

        if mean < 80:
            factor = min(1.8, 100 / max(mean, 20))
            result = frame.astype(np.float32) * factor
            return np.clip(result, 0, 255).astype(np.uint8)
        elif mean > 180:
            factor = max(0.5, 180 / mean)
            result = frame.astype(np.float32) * factor
            return np.clip(result, 0, 255).astype(np.uint8)

        return frame

    @staticmethod
    def _auto_white_balance(frame: np.ndarray) -> np.ndarray:
        if len(frame.shape) < 3:
            return frame

        result = frame.astype(np.float32)
        b, g, r = cv2.split(result)

        mean_b, mean_g, mean_r = b.mean(), g.mean(), r.mean()
        mean_gray = (mean_b + mean_g + mean_r) / 3

        if mean_b > 0:
            b *= mean_gray / mean_b
        if mean_g > 0:
            g *= mean_gray / mean_g
        if mean_r > 0:
            r *= mean_gray / mean_r

        result = cv2.merge([b, g, r])
        return np.clip(result, 0, 255).astype(np.uint8)

    @staticmethod
    def _adjust_saturation(frame: np.ndarray, factor: float) -> np.ndarray:
        if len(frame.shape) < 3:
            return frame
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV).astype(np.float32)
        hsv[:, :, 1] = np.clip(hsv[:, :, 1] * factor, 0, 255)
        return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    @staticmethod
    def _apply_vibrance(frame: np.ndarray) -> np.ndarray:
        if len(frame.shape) < 3:
            return frame
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV).astype(np.float32)
        sat = hsv[:, :, 1]
        boost = 1.0 + (1.0 - sat / 255.0) * 0.5
        hsv[:, :, 1] = np.clip(sat * boost, 0, 255)
        return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    @staticmethod
    def _skin_smooth(frame: np.ndarray) -> np.ndarray:
        ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
        skin_mask = cv2.inRange(
            ycrcb,
            np.array([0, 133, 77], dtype=np.uint8),
            np.array([255, 173, 127], dtype=np.uint8)
        )
        smoothed = cv2.bilateralFilter(frame, 9, 75, 75)
        mask_3ch = cv2.cvtColor(skin_mask, cv2.COLOR_GRAY2BGR).astype(np.float32) / 255.0
        result = (smoothed * mask_3ch + frame * (1 - mask_3ch)).astype(np.uint8)
        return result

    @classmethod
    def _get_vignette_mask(cls, rows: int, cols: int, strength: float) -> np.ndarray:
        key = (rows, cols, round(strength, 2))
        if key in cls._vignette_cache:
            return cls._vignette_cache[key]

        kernel_x = cv2.getGaussianKernel(cols, cols * 0.6)
        kernel_y = cv2.getGaussianKernel(rows, rows * 0.6)
        kernel = kernel_y * kernel_x.T
        mask = kernel / kernel.max()

        if strength < 0:
            mask = 1.0 + mask * strength
        else:
            mask = mask * strength + (1 - strength)

        if len(cls._vignette_cache) >= cls._MAX_VIGNETTE_CACHE:
            cls._vignette_cache.clear()

        cls._vignette_cache[key] = mask
        return mask

    @staticmethod
    def _apply_vignette(frame: np.ndarray, strength: float = -0.2) -> np.ndarray:
        rows, cols = frame.shape[:2]
        mask = ImageEnhancer._get_vignette_mask(rows, cols, strength)

        if len(frame.shape) == 3:
            mask = cv2.merge([mask, mask, mask])

        result = frame.astype(np.float32) * mask
        return np.clip(result, 0, 255).astype(np.uint8)

    @staticmethod
    def _binarize_document(frame: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
        denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
        binary = cv2.adaptiveThreshold(
            denoised, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 15, 8
        )
        return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)

    # ==================== COMPATIBILIDAD ====================

    @staticmethod
    def _auto_enhance(gray: np.ndarray) -> np.ndarray:
        enhanced = ImageEnhancer._apply_clahe(gray)
        denoised = cv2.fastNlMeansDenoising(enhanced, None, 10, 7, 21)
        _, binary = cv2.threshold(denoised, 0, 255,
                                  cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return binary

    @staticmethod
    def _enhance_contrast(gray: np.ndarray) -> np.ndarray:
        return ImageEnhancer._apply_clahe(gray)

    @staticmethod
    def _binarize(gray: np.ndarray) -> np.ndarray:
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        return cv2.adaptiveThreshold(
            blurred, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2
        )

    @staticmethod
    def rotate_if_needed(frame: np.ndarray) -> np.ndarray:
        """Detecta y corrige orientación con Tesseract OSD"""
        try:
            import pytesseract
            from pytesseract import Output

            try:
                osd = pytesseract.image_to_osd(frame, output_type=Output.DICT)
                rotation = osd.get('rotate', 0)

                if rotation == 90:
                    return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                elif rotation == 180:
                    return cv2.rotate(frame, cv2.ROTATE_180)
                elif rotation == 270:
                    return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
            except Exception:
                pass
            return frame
        except ImportError:
            return frame

    @classmethod
    def clear_caches(cls):
        """Limpia todas las cachés internas"""
        cls._shared_clahe = None
        cls._gamma_lut_cache.clear()
        cls._vignette_cache.clear()
        logger.info("🗑️ Cachés de ImageEnhancer limpiadas")

    @classmethod
    def reload_config(cls):
        """Recarga la config desde advanced_config"""
        from utils.config_loader import advanced_config
        advanced_config.reload()
        cls.clear_caches()
        logger.info("🔄 ImageEnhancer recargado")
        return True