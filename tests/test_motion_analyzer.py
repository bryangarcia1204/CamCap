"""
Tests para el MotionAnalyzer de FASE 3.1.
"""
import pytest
import numpy as np
import time

from plugins.motion_detector.analyzer import MotionAnalyzer
from core.extensions.interfaces import FrameAnalyzer
from core.plugin_api.interfaces import PluginContext


@pytest.fixture
def plugin_context():
    """Contexto mínimo para el analyzer."""
    ctx = PluginContext()
    ctx.is_debug = False
    return ctx


@pytest.fixture
def analyzer(plugin_context):
    """Analyzer listo para tests."""
    return MotionAnalyzer(plugin_context)


class TestMotionAnalyzerInit:
    def test_crea_sin_errores(self, analyzer):
        assert analyzer is not None
        assert analyzer._detectors == {}
        assert analyzer._enabled_cache == {}

    def test_implementa_protocolo(self, analyzer):
        """Debe cumplir FrameAnalyzer."""
        assert isinstance(analyzer, FrameAnalyzer)


class TestShouldRun:
    def test_default_disabled(self, analyzer):
        """Sin config, motion_enabled=False por default."""
        assert analyzer.should_run(0) is False

    def test_cache_evita_lecturas(self, analyzer, monkeypatch):
        """Verifica que hace cache de should_run."""
        call_count = [0]

        def fake_get():
            call_count[0] += 1
            return {"motion_enabled": True}

        monkeypatch.setattr(
            "core.settings_manager.settings_manager.get_detection_settings",
            fake_get,
        )

        # Primera llamada carga config
        analyzer.should_run(0)
        assert call_count[0] == 1

        # Segunda llamada usa cache (dentro de 2s)
        analyzer.should_run(0)
        assert call_count[0] == 1

        # Forzar expiración del cache
        analyzer._last_check[0] = 0
        analyzer.should_run(0)
        assert call_count[0] == 2


class TestAnalyze:
    def test_frame_vacio_retorna_none(self, analyzer):
        assert analyzer.analyze(0, np.array([])) is None
        assert analyzer.analyze(0, None) is None

    def test_frame_sin_detector_crea_uno(self, analyzer):
        """La primera llamada debe crear el detector."""
        frame = np.full((480, 640, 3), 128, dtype=np.uint8)

        # Forzar motion_enabled
        analyzer._enabled_cache[0] = True
        analyzer._last_check[0] = time.time()

        result = analyzer.analyze(0, frame)

        assert 0 in analyzer._detectors
        assert result is not None
        assert result["kind"] == "motion"
        assert "rects" in result
        assert "intensity" in result

    def test_analyze_con_frame_negro(self, analyzer):
        """Frame negro no debe dar error."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        analyzer._enabled_cache[0] = True
        analyzer._last_check[0] = time.time()

        result = analyzer.analyze(0, frame)
        assert result is not None
        assert result["kind"] == "motion"


class TestCleanup:
    def test_cleanup_camara_especifica(self, analyzer):
        analyzer._detectors[1] = "fake"
        analyzer._detectors[2] = "fake"
        analyzer._enabled_cache[1] = True
        analyzer._enabled_cache[2] = True

        analyzer.cleanup(camera_id=1)

        assert 1 not in analyzer._detectors
        assert 2 in analyzer._detectors
        assert 1 not in analyzer._enabled_cache
        assert 2 in analyzer._enabled_cache

    def test_cleanup_todo(self, analyzer):
        analyzer._detectors[1] = "fake"
        analyzer._detectors[2] = "fake"

        analyzer.cleanup()

        assert len(analyzer._detectors) == 0


class TestGetFrameSkip:
    def test_retorna_entero(self, analyzer):
        skip = analyzer.get_frame_skip()
        assert isinstance(skip, int)
        assert skip >= 1


class TestRegistryIntegration:
    def test_se_puede_registrar(self, plugin_context):
        """Verifica que se puede registrar en el registry."""
        from core.extension_registry import ExtensionRegistry, set_extension_registry
        from core.extensions.interfaces import FrameAnalyzer

        registry = ExtensionRegistry()
        set_extension_registry(registry)

        analyzer = MotionAnalyzer(plugin_context)
        registry.register(FrameAnalyzer, analyzer, owner="test")

        analyzers = registry.get(FrameAnalyzer)
        assert len(analyzers) == 1
        assert analyzers[0] is analyzer

        # Cleanup
        registry.unregister(FrameAnalyzer, analyzer)
        assert len(registry.get(FrameAnalyzer)) == 0