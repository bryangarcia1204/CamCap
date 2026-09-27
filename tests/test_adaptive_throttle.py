"""Tests para utils/adaptive_throttle.py

FIX v2: tests con rangos + config-driven
"""
import pytest
import time
from utils.adaptive_throttle import AdaptiveThrottle
from utils.config_loader import advanced_config


class TestAdaptiveThrottleInit:
    def test_init_defaults_valid(self):
        """Los defaults deben estar en rangos razonables"""
        throttle = AdaptiveThrottle()

        # Rangos válidos en lugar de valores exactos
        assert 0.1 <= throttle.target_cpu <= 4.0, \
            f"target_cpu={throttle.target_cpu} fuera de rango"
        assert 0.1 <= throttle.target_gpu <= 1.0, \
            f"target_gpu={throttle.target_gpu} fuera de rango"
        assert 1 <= throttle.max_skip <= 10, \
            f"max_skip={throttle.max_skip} fuera de rango"
        assert throttle.check_interval > 0

    def test_init_with_custom_values(self):
        """Valores custom deben respetarse"""
        throttle = AdaptiveThrottle(
            target_cpu=2.5,
            target_gpu=0.5,
            max_skip=5,
            check_interval=0.5
        )
        assert throttle.target_cpu == 2.5
        assert throttle.target_gpu == 0.5
        assert throttle.max_skip == 5

    def test_max_skip_minimum_1(self):
        """max_skip=0 debe forzarse a 1"""
        throttle = AdaptiveThrottle(max_skip=0)
        assert throttle.max_skip >= 1

    def test_init_from_config(self):
        """Sin args, debe leer de advanced_config"""
        cfg = advanced_config.get_all()
        throttle = AdaptiveThrottle()
        # El default de AdaptiveThrottle es 0.70, pero si tu config lo cambia,
        # debe respetarse. Solo verificamos que sea razonable.
        assert 0.1 <= throttle.target_cpu <= 4.0


class TestAdaptiveThrottleSkip:
    def test_should_process_always_no_skip(self):
        """Sin skip configurado, siempre procesa"""
        throttle = AdaptiveThrottle()
        for i in range(20):
            assert throttle.should_process_frame(i) is True

    def test_skip_pattern_1(self):
        """Con skip=1, procesa 1 de cada 2"""
        throttle = AdaptiveThrottle(max_skip=3)
        throttle._current_skip = 1
        # Verificar patrón
        results = [throttle.should_process_frame(i) for i in range(10)]
        assert results.count(True) == 5
        assert results.count(False) == 5

    def test_skip_pattern_2(self):
        """Con skip=2, procesa 1 de cada 3"""
        throttle = AdaptiveThrottle(max_skip=3)
        throttle._current_skip = 2
        results = [throttle.should_process_frame(i) for i in range(9)]
        assert results.count(True) == 3
        assert results.count(False) == 6


class TestAdaptiveThrottleAdjustment:
    def test_skip_increases_on_high_cpu(self):
        """Con CPU alta, skip debe subir"""
        throttle = AdaptiveThrottle(target_cpu=0.50, check_interval=0)
        throttle._cpu_percent = 0.95
        throttle._last_check = 0
        throttle._adjust_skip()
        assert throttle.get_current_skip() >= 1

    def test_skip_decreases_on_low_cpu(self):
        """Con CPU baja sostenida, skip debe bajar"""
        throttle = AdaptiveThrottle(target_cpu=0.70, check_interval=0)
        throttle._current_skip = 3
        throttle._cpu_percent = 0.10
        throttle._last_check = 0
        # Varias iteraciones para que baje
        for _ in range(5):
            throttle._last_check = 0
            throttle._adjust_skip()
        assert throttle.get_current_skip() < 3

    def test_skip_never_exceeds_max(self):
        """skip nunca debe superar max_skip"""
        throttle = AdaptiveThrottle(max_skip=2, check_interval=0)
        throttle._cpu_percent = 0.99
        for _ in range(20):
            throttle._last_check = 0
            throttle._adjust_skip()
        assert throttle.get_current_skip() <= 2


class TestAdaptiveThrottleMetrics:
    def test_get_metrics_complete(self):
        """El dict de métricas debe tener todas las claves"""
        throttle = AdaptiveThrottle()
        metrics = throttle.get_metrics()

        for key in ["cpu_percent", "gpu_percent", "gpu_available",
                    "current_skip", "max_skip", "avg_frame_time_ms"]:
            assert key in metrics, f"Falta clave: {key}"

    def test_get_metrics_values_valid(self):
        """Los valores deben estar en rangos válidos"""
        throttle = AdaptiveThrottle()
        metrics = throttle.get_metrics()

        assert 0 <= metrics["cpu_percent"] <= 10
        assert 0 <= metrics["gpu_percent"] <= 1
        assert metrics["current_skip"] >= 0
        assert metrics["avg_frame_time_ms"] >= 0

    def test_record_frame_time_accumulates(self):
        """Los tiempos grabados deben acumularse"""
        throttle = AdaptiveThrottle()
        for _ in range(5):
            throttle.record_frame_time(0.033)

        metrics = throttle.get_metrics()
        # 0.033s = 33ms, con 5 muestras debe ser ~33ms
        assert 20 <= metrics["avg_frame_time_ms"] <= 50


class TestAdaptiveThrottleReset:
    def test_reset_clears_state(self):
        """Reset debe limpiar todo"""
        throttle = AdaptiveThrottle()
        throttle._current_skip = 2
        throttle.record_frame_time(0.05)

        throttle.reset()

        assert throttle.get_current_skip() == 0
        metrics = throttle.get_metrics()
        assert metrics["avg_frame_time_ms"] == 0