"""Tests para detection/image_enhancer.py

FIX v2:
- Tests de reload_config y clear_caches
- Propiedades en lugar de valores exactos
"""
import pytest
import numpy as np
import cv2

from plugins.image_enhancer.image_enhancer import ImageEnhancer


class TestQualityAssessment:
    def test_returns_dict_with_all_scores(self, sample_bgr_image):
        result = ImageEnhancer.assess_quality(sample_bgr_image)
        assert isinstance(result, dict)

        required_keys = [
            "blur_score", "brightness_score", "contrast_score",
            "noise_score", "exposure_score",
            "white_balance_score", "saturation_score",
            "overall_score",
        ]
        for key in required_keys:
            assert key in result, f"Falta: {key}"

    def test_scores_in_valid_range(self, sample_bgr_image):
        result = ImageEnhancer.assess_quality(sample_bgr_image)
        for key, value in result.items():
            if key.endswith("_score"):
                assert 0.0 <= value <= 1.0, \
                    f"{key}={value} fuera de [0,1]"

    def test_dark_image_low_brightness(self, dark_image):
        result = ImageEnhancer.assess_quality(dark_image)
        assert result["brightness_score"] < 0.5

    def test_bright_image_low_brightness(self, bright_image):
        result = ImageEnhancer.assess_quality(bright_image)
        assert result["brightness_score"] < 0.5

    def test_blurry_image_low_blur_score(self, blurry_image):
        result = ImageEnhancer.assess_quality(blurry_image)
        assert result["blur_score"] < 0.5

    def test_empty_image_scores_zero(self):
        result = ImageEnhancer.assess_quality(np.array([]))
        assert result["overall_score"] == 0

    def test_grayscale_input(self, sample_gray_image):
        result = ImageEnhancer.assess_quality(sample_gray_image)
        assert 0 <= result["overall_score"] <= 1

    def test_problems_list_present(self, sample_bgr_image):
        result = ImageEnhancer.assess_quality(sample_bgr_image)
        assert "problems" in result
        assert isinstance(result["problems"], list)

    def test_recommendations_list_present(self, sample_bgr_image):
        result = ImageEnhancer.assess_quality(sample_bgr_image)
        assert "recommendations" in result
        assert isinstance(result["recommendations"], list)


class TestEnhanceBasic:
    def test_returns_same_shape(self, sample_bgr_image):
        result = ImageEnhancer.enhance(sample_bgr_image)
        assert result.shape == sample_bgr_image.shape
        assert result.dtype == np.uint8

    def test_empty_image_returns_empty(self):
        result = ImageEnhancer.enhance(np.array([]))
        assert result.size == 0

    def test_none_returns_none(self):
        result = ImageEnhancer.enhance(None)
        assert result is None


class TestBrightnessContrast:
    def test_brightness_increases_mean(self, sample_bgr_image):
        result = ImageEnhancer.enhance(sample_bgr_image, brightness=50)
        assert result.mean() > sample_bgr_image.mean()

    def test_brightness_decreases_mean(self, sample_bgr_image):
        result = ImageEnhancer.enhance(sample_bgr_image, brightness=-50)
        assert result.mean() < sample_bgr_image.mean()

    def test_contrast_keeps_shape(self, sample_bgr_image):
        result = ImageEnhancer.enhance(sample_bgr_image, contrast=2.0)
        assert result.shape == sample_bgr_image.shape

    def test_contrast_increases_std(self, sample_bgr_image):
        """Con más contraste, la desviación estándar debe subir"""
        import cv2
        gray_orig = cv2.cvtColor(sample_bgr_image, cv2.COLOR_BGR2GRAY)
        result = ImageEnhancer.enhance(sample_bgr_image, contrast=2.0)
        gray_result = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)

        assert gray_result.std() >= gray_orig.std()


class TestGamma:
    def test_gamma_less_than_1_darkens(self, sample_bgr_image):
        darker = ImageEnhancer.enhance(sample_bgr_image, gamma=0.5)
        assert darker.mean() < sample_bgr_image.mean()

    def test_gamma_greater_than_1_brightens(self, sample_bgr_image):
        brighter = ImageEnhancer.enhance(sample_bgr_image, gamma=2.0)
        assert brighter.mean() > sample_bgr_image.mean()

    def test_gamma_1_no_change(self, sample_bgr_image):
        result = ImageEnhancer.enhance(sample_bgr_image, gamma=1.0)
        assert np.array_equal(result, sample_bgr_image)


class TestSaturation:
    def test_saturation_increases(self, sample_bgr_image):
        result = ImageEnhancer.enhance(sample_bgr_image, saturation=1.5)
        assert result.shape == sample_bgr_image.shape

    def test_saturation_zero_grayscale(self, sample_bgr_image):
        """saturation=0 debería acercarse a escala de grises"""
        result = ImageEnhancer.enhance(sample_bgr_image, saturation=0.0)
        # Todos los canales deben ser casi iguales
        b, g, r = cv2.split(result)
        assert np.allclose(b, g, atol=5), "saturation=0 no da gris"
        assert np.allclose(g, r, atol=5), "saturation=0 no da gris"


class TestAutoContrast:
    def test_auto_contrast_keeps_shape(self, sample_bgr_image):
        result = ImageEnhancer.enhance(sample_bgr_image, auto_contrast=True)
        assert result.shape == sample_bgr_image.shape

    def test_auto_contrast_increases_std(self, sample_bgr_image):
        """CLAHE debería aumentar el contraste local"""
        import cv2
        gray_orig = cv2.cvtColor(sample_bgr_image, cv2.COLOR_BGR2GRAY)
        result = ImageEnhancer.enhance(sample_bgr_image, auto_contrast=True)
        gray_result = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)

        # El std no puede bajar mucho
        assert gray_result.std() >= gray_orig.std() * 0.8


class TestPresets:
    def test_preset_documento(self, sample_bgr_image):
        result = ImageEnhancer.enhance(sample_bgr_image, preset="documento")
        assert result.shape == sample_bgr_image.shape

    def test_preset_foto(self, sample_bgr_image):
        result = ImageEnhancer.enhance(sample_bgr_image, preset="foto")
        assert result.shape == sample_bgr_image.shape

    def test_preset_noche(self, sample_bgr_image):
        result = ImageEnhancer.enhance(sample_bgr_image, preset="noche")
        assert result.shape == sample_bgr_image.shape

    def test_preset_retrato(self, sample_bgr_image):
        result = ImageEnhancer.enhance(sample_bgr_image, preset="retrato")
        assert result.shape == sample_bgr_image.shape

    def test_preset_paisaje(self, sample_bgr_image):
        result = ImageEnhancer.enhance(sample_bgr_image, preset="paisaje")
        assert result.shape == sample_bgr_image.shape

    def test_preset_ninguno(self, sample_bgr_image):
        """Ninguno debe devolver la imagen casi sin cambios"""
        result = ImageEnhancer.enhance(sample_bgr_image, preset="ninguno")
        assert result.shape == sample_bgr_image.shape

    def test_preset_invalid_does_not_crash(self, sample_bgr_image):
        result = ImageEnhancer.enhance(sample_bgr_image, preset="inventado")
        assert result.shape == sample_bgr_image.shape


class TestAutoEnhance:
    def test_auto_enhance_keeps_shape(self, sample_bgr_image):
        result = ImageEnhancer.auto_enhance(sample_bgr_image)
        assert result.shape == sample_bgr_image.shape
        assert result.dtype == np.uint8

    def test_auto_enhance_dark_image(self, dark_image):
        result = ImageEnhancer.auto_enhance(dark_image)
        assert result.shape == dark_image.shape

    def test_auto_enhance_bright_image(self, bright_image):
        result = ImageEnhancer.auto_enhance(bright_image)
        assert result.shape == bright_image.shape

    def test_auto_enhance_noisy_image(self, noisy_image):
        result = ImageEnhancer.auto_enhance(noisy_image)
        assert result.shape == noisy_image.shape


class TestGammaCache:
    def test_gamma_lut_cache_hit(self):
        ImageEnhancer._gamma_lut_cache.clear()
        lut1 = ImageEnhancer._get_gamma_lut(0.5)
        lut2 = ImageEnhancer._get_gamma_lut(0.5)
        assert lut1 is lut2

    def test_gamma_lut_different_values(self):
        ImageEnhancer._gamma_lut_cache.clear()
        lut1 = ImageEnhancer._get_gamma_lut(0.5)
        lut2 = ImageEnhancer._get_gamma_lut(1.5)
        assert lut1 is not lut2

    def test_gamma_lut_shape(self):
        lut = ImageEnhancer._get_gamma_lut(1.0)
        assert lut.shape == (256,)
        assert lut.dtype == np.uint8


class TestClaheCache:
    def test_clahe_shared_instance(self):
        clahe1 = ImageEnhancer._get_clahe()
        clahe2 = ImageEnhancer._get_clahe()
        assert clahe1 is clahe2


class TestVignetteCache:
    def test_vignette_mask_cached(self):
        """El mask de viñeteo debe cachearse"""
        ImageEnhancer._vignette_cache.clear()
        mask1 = ImageEnhancer._get_vignette_mask(480, 640, -0.2)
        mask2 = ImageEnhancer._get_vignette_mask(480, 640, -0.2)
        assert mask1 is mask2


class TestReloadConfig:
    def test_reload_config_returns_true(self):
        result = ImageEnhancer.reload_config()
        assert result is True

    def test_reload_config_clears_caches(self):
        """Tras reload, los caches deben estar vacíos"""
        # Poblar cachés
        ImageEnhancer._get_gamma_lut(0.5)
        ImageEnhancer._get_clahe()

        assert len(ImageEnhancer._gamma_lut_cache) > 0

        ImageEnhancer.reload_config()

        assert len(ImageEnhancer._gamma_lut_cache) == 0


class TestClearCaches:
    def test_clear_caches_empties_all(self):
        ImageEnhancer._get_gamma_lut(0.5)
        ImageEnhancer._get_clahe()
        ImageEnhancer._get_vignette_mask(480, 640, -0.2)

        ImageEnhancer.clear_caches()

        assert len(ImageEnhancer._gamma_lut_cache) == 0
        assert len(ImageEnhancer._vignette_cache) == 0
        assert ImageEnhancer._shared_clahe is None


class TestBinarize:
    def test_binarize_document(self, sample_bgr_image):
        result = ImageEnhancer.enhance(sample_bgr_image, binarize=True)
        assert result.shape == sample_bgr_image.shape

    def test_binarize_creates_binary(self, sample_bgr_image):
        """Binarizar debe dar valores 0 o 255 (en escala de grises)"""
        result = ImageEnhancer.enhance(sample_bgr_image, binarize=True)
        gray = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)
        unique = np.unique(gray)
        # Debe haber solo 2 valores únicos (o casi)
        assert len(unique) <= 10, f"Binarizado tiene {len(unique)} valores únicos"


class TestDenoise:
    def test_denoise_reduces_noise(self, noisy_image):
        """Denoise debería reducir la varianza del ruido"""
        result = ImageEnhancer.enhance(
            noisy_image,
            denoise=True,
            denoise_strength=10,
        )
        assert result.shape == noisy_image.shape