"""Tests para detection/motion_detector.py

FIX v2: tests con métodos más directos + más frames
"""
import pytest
import numpy as np
import time

from detection.motion_detector import MotionDetector


class TestMotionDetectorInit:
    def test_init_defaults_reasonable(self):
        """Los defaults deben estar en rangos razonables"""
        detector = MotionDetector()

        assert 1 <= detector.sensitivity <= 100
        assert detector.min_area > 0
        assert detector.cooldown_seconds > 0
        assert detector.method in ("adaptive", "mog2", "frame_diff")

    def test_init_custom(self):
        detector = MotionDetector(
            sensitivity=50,
            min_area=1000,
            cooldown_seconds=2.0,
            method="mog2"
        )
        assert detector.sensitivity == 50
        assert detector.min_area == 1000
        assert detector.method == "mog2"


class TestMotionDetectorEdgeCases:
    def test_detect_empty_frame(self):
        detector = MotionDetector()
        has_motion, rects, mask = detector.detect(np.array([]))
        assert has_motion is False
        assert rects == []

    def test_detect_none_frame(self):
        detector = MotionDetector()
        has_motion, rects, mask = detector.detect(None)
        assert has_motion is False

    def test_detect_single_frame_no_crash(self):
        detector = MotionDetector()
        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        # No debe crashear
        detector.detect(frame)


class TestMotionDetectorStaticScene:
    def test_no_motion_with_static_frames(self):
        """Con frames idénticos, no debe haber movimiento"""
        detector = MotionDetector(
            min_consecutive_frames=1,
            method="mog2"  # Más predecible que adaptive
        )
        static = np.full((480, 640, 3), 128, dtype=np.uint8)

        # Establecer fondo con muchos frames
        for _ in range(30):
            detector.detect(static)

        # Verificar que no hay movimiento
        has_motion, rects, _ = detector.detect(static)
        assert has_motion is False, \
            f"Falso positivo: {len(rects)} rects detectados"


class TestMotionDetectorMovement:
    def test_detect_movement_with_mog2(self):
        """Método directo para detectar movimiento"""
        detector = MotionDetector(
            min_consecutive_frames=1,
            method="mog2",
            sensitivity=25,
            min_area=500,
        )

        static = np.full((480, 640, 3), 128, dtype=np.uint8)

        # Establecer fondo
        for _ in range(30):
            detector.detect(static)

        # Mover objeto durante varios frames
        has_motion_detected = False
        for i in range(30):
            moving = static.copy()
            x = 100 + i * 15
            y = 200
            moving[y:y+150, x:x+150] = 255

            has_motion, rects, _ = detector.detect(moving)
            if has_motion:
                has_motion_detected = True
                break

        assert has_motion_detected, \
            "No se detectó movimiento con MOG2 en 30 frames"


class TestMotionDetectorCooldown:
    def test_can_notify_initial(self):
        detector = MotionDetector(cooldown_seconds=0.5)
        assert detector.can_notify() is True

    def test_can_notify_blocks_after_call(self):
        detector = MotionDetector(cooldown_seconds=0.5)
        detector.can_notify()
        # Segunda llamada inmediata debe bloquearse
        assert detector.can_notify() is False

    def test_can_notify_after_cooldown(self):
        detector = MotionDetector(cooldown_seconds=0.3)
        detector.can_notify()
        time.sleep(0.4)
        assert detector.can_notify() is True


class TestMotionDetectorReset:
    def test_reset_clears_state(self):
        detector = MotionDetector()
        detector.total_detections = 5
        detector.motion_intensity = 0.8
        detector.reset()
        assert detector.total_detections == 0
        assert detector.motion_intensity == 0.0


class TestMotionDetectorCLAHE:
    def test_clahe_cached(self):
        """El CLAHE debe compartirse entre instancias"""
        d1 = MotionDetector()
        d2 = MotionDetector()
        assert d1._get_clahe() is d2._get_clahe()


class TestMotionDetectorDrawing:
    def test_draw_empty_rects(self, sample_bgr_image):
        detector = MotionDetector()
        result = detector.draw_motion_rects(sample_bgr_image, [])
        assert result.shape == sample_bgr_image.shape

    def test_draw_with_rects(self, sample_bgr_image):
        detector = MotionDetector()
        rects = [(100, 100, 50, 50), (200, 200, 30, 30)]
        result = detector.draw_motion_rects(sample_bgr_image, rects)
        assert result.shape == sample_bgr_image.shape
        # Verificar que se dibujó algo (los píxeles cambiaron)
        assert not np.array_equal(result, sample_bgr_image)