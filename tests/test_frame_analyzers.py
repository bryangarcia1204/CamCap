"""
Tests para los FrameAnalyzers de FASE 3.
"""
import pytest
import numpy as np
import time

from plugins.motion_detector.analyzer import MotionAnalyzer
from plugins.face_recognizer.analyzer import FaceAnalyzer
from plugins.document_scanner.analyzer import DocumentAnalyzer
from core.extensions.interfaces import FrameAnalyzer
from core.plugin_api.interfaces import PluginContext


@pytest.fixture
def plugin_context():
    ctx = PluginContext()
    ctx.is_debug = False
    return ctx


# ==================== MotionAnalyzer ====================

class TestMotionAnalyzer:
    def test_implementa_protocolo(self, plugin_context):
        analyzer = MotionAnalyzer(plugin_context)
        assert isinstance(analyzer, FrameAnalyzer)

    def test_should_run_default_disabled(self, plugin_context):
        analyzer = MotionAnalyzer(plugin_context)
        assert analyzer.should_run(0) is False

    def test_frame_vacio_retorna_none(self, plugin_context):
        analyzer = MotionAnalyzer(plugin_context)
        assert analyzer.analyze(0, np.array([])) is None
        assert analyzer.analyze(0, None) is None

    def test_analyze_crea_detector(self, plugin_context):
        analyzer = MotionAnalyzer(plugin_context)
        analyzer._enabled_cache[0] = True
        analyzer._last_check[0] = time.time()
        frame = np.full((480, 640, 3), 128, dtype=np.uint8)

        result = analyzer.analyze(0, frame)
        assert 0 in analyzer._detectors
        assert result is not None
        assert result["kind"] == "motion"

    def test_cleanup_camara(self, plugin_context):
        analyzer = MotionAnalyzer(plugin_context)
        analyzer._detectors[1] = "fake"
        analyzer._detectors[2] = "fake"
        analyzer.cleanup(camera_id=1)
        assert 1 not in analyzer._detectors
        assert 2 in analyzer._detectors


# ==================== FaceAnalyzer ====================

class TestFaceAnalyzer:
    def test_implementa_protocolo(self, plugin_context):
        analyzer = FaceAnalyzer(plugin_context)
        assert isinstance(analyzer, FrameAnalyzer)

    def test_should_run_default_disabled(self, plugin_context):
        analyzer = FaceAnalyzer(plugin_context)
        assert analyzer.should_run(0) is False

    def test_cooldown_bloquea(self, plugin_context):
        analyzer = FaceAnalyzer(plugin_context)
        analyzer._enabled_cache[0] = True
        analyzer._last_check[0] = time.time()

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        # Primera llamada
        analyzer.analyze(0, frame)
        # Segunda llamada inmediata → debe retornar None por cooldown
        result = analyzer.analyze(0, frame)
        assert result is None

    def test_cleanup(self, plugin_context):
        analyzer = FaceAnalyzer(plugin_context)
        analyzer._recognizers[1] = "fake"
        analyzer.cleanup(camera_id=1)
        assert 1 not in analyzer._recognizers


# ==================== DocumentAnalyzer ====================

class TestDocumentAnalyzer:
    def test_implementa_protocolo(self, plugin_context):
        analyzer = DocumentAnalyzer(plugin_context)
        assert isinstance(analyzer, FrameAnalyzer)

    def test_should_run_default_disabled(self, plugin_context):
        analyzer = DocumentAnalyzer(plugin_context)
        assert analyzer.should_run(0) is False

    def test_frame_skip_aplicado(self, plugin_context):
        analyzer = DocumentAnalyzer(plugin_context)
        analyzer._enabled_cache[0] = True
        analyzer._last_check[0] = time.time()
        analyzer._config_cache = {"scan_frame_skip": 3}
        analyzer._config_last_load = time.time()

        # Contador: 1 → False (1%3 != 0)
        assert analyzer.should_run(0) is False
        # 2 → False
        assert analyzer.should_run(0) is False
        # 3 → True
        assert analyzer.should_run(0) is True

    def test_frame_vacio_retorna_none(self, plugin_context):
        analyzer = DocumentAnalyzer(plugin_context)
        assert analyzer.analyze(0, np.array([])) is None


# ==================== Integración con Registry ====================

class TestRegistryIntegration:
    def test_registrar_los_3(self, plugin_context):
        from core.extension_registry import ExtensionRegistry, set_extension_registry
        from core.extensions.interfaces import FrameAnalyzer

        registry = ExtensionRegistry()
        set_extension_registry(registry)

        m = MotionAnalyzer(plugin_context)
        f = FaceAnalyzer(plugin_context)
        d = DocumentAnalyzer(plugin_context)

        registry.register(FrameAnalyzer, m, priority=100)
        registry.register(FrameAnalyzer, f, priority=110)
        registry.register(FrameAnalyzer, d, priority=130)

        analyzers = registry.get(FrameAnalyzer)
        assert len(analyzers) == 3
        # Orden por prioridad
        assert analyzers[0] is m
        assert analyzers[1] is f
        assert analyzers[2] is d