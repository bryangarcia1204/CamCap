"""
Tests de integración: FramesAPIImpl + ExtensionRegistry.

Verifica que:
- Los callbacks registrados vía FramesAPIImpl se aplican
- Los FramePreProcessor del registry se aplican
- La prioridad se respeta
- Los errores no rompen el pipeline
"""
import pytest
import numpy as np

from core.extension_registry import ExtensionRegistry, set_extension_registry
from core.extensions.interfaces import FramePreProcessor, FramePostProcessor
from core.plugin_api.api_impl import FramesAPIImpl, CamerasAPIImpl


@pytest.fixture
def clean_registry():
    """Registry limpio para cada test."""
    registry = ExtensionRegistry()
    set_extension_registry(registry)
    yield registry
    registry.clear()


class TestFramesAPIRegistryIntegration:

    def test_register_pre_processor_via_api(self, clean_registry):
        """Registrar vía API debe añadir al registry."""
        api = FramesAPIImpl()

        def processor(camera_id, frame):
            return frame + 1

        api.register_pre_processor(processor)

        # Verificar que está en el registry
        processors = clean_registry.get(FramePreProcessor)
        assert len(processors) == 1

    def test_apply_pre_processor_from_registry(self, clean_registry):
        """Los processors del registry deben aplicarse."""
        api = FramesAPIImpl()

        def processor(camera_id, frame):
            return frame + 10

        api.register_pre_processor(processor)

        frame = np.array([[1]], dtype=np.int32)
        result = api.apply_pre_processors(0, frame)

        assert result[0][0] == 11

    def test_multiple_processors_priority(self, clean_registry):
        """Los processors deben ejecutarse en orden de prioridad."""
        api = FramesAPIImpl()
        calls = []

        def first(cid, f):
            calls.append("first")
            return f + 1

        def second(cid, f):
            calls.append("second")
            return f * 2

        api.register_pre_processor(first, priority=10)
        api.register_pre_processor(second, priority=20)

        frame = np.array([[1]], dtype=np.int32)
        result = api.apply_pre_processors(0, frame)

        assert calls == ["first", "second"]
        assert result[0][0] == (1 + 1) * 2

    def test_processor_from_extension_registry_directly(self, clean_registry):
        """
        Un FramePreProcessor registrado DIRECTAMENTE en el registry
        (no vía FramesAPIImpl) también debe aplicarse.
        """
        class MyProcessor:
            def process(self, camera_id, frame):
                return frame + 100

            def get_priority(self):
                return 50

        clean_registry.register(FramePreProcessor, MyProcessor())

        api = FramesAPIImpl()
        frame = np.array([[1]], dtype=np.int32)
        result = api.apply_pre_processors(0, frame)

        assert result[0][0] == 101

    def test_mixed_api_and_registry_processors(self, clean_registry):
        """Ambos sistemas deben coexistir."""
        api = FramesAPIImpl()

        # Vía API
        api.register_pre_processor(lambda cid, f: f + 1, priority=10)

        # Vía registry directo
        class MyProcessor:
            def process(self, camera_id, frame):
                return frame * 2

            def get_priority(self):
                return 20

        clean_registry.register(FramePreProcessor, MyProcessor())

        frame = np.array([[1]], dtype=np.int32)
        result = api.apply_pre_processors(0, frame)

        # (1 + 1) * 2 = 4
        assert result[0][0] == 4

    def test_processor_error_does_not_break_pipeline(self, clean_registry):
        """Un processor que falla no debe romper los demás."""
        api = FramesAPIImpl()

        def bad(cid, f):
            raise ValueError("Test error")

        def good(cid, f):
            return f + 1

        api.register_pre_processor(bad, priority=10)
        api.register_pre_processor(good, priority=20)

        frame = np.array([[1]], dtype=np.int32)
        result = api.apply_pre_processors(0, frame)

        # El bueno debe haber corrido
        assert result[0][0] == 2

    def test_post_processor(self, clean_registry):
        """Los post-processors deben aplicarse."""
        api = FramesAPIImpl()
        called = []

        def post(cid, f):
            called.append(cid)

        api.register_post_processor(post)

        frame = np.array([[1]], dtype=np.int32)
        api.apply_post_processors(5, frame)

        assert called == [5]

    def test_registry_disabled_processor_not_applied(self, clean_registry):
        """Un processor desactivado no debe aplicarse."""
        api = FramesAPIImpl()

        class MyProcessor:
            def process(self, camera_id, frame):
                return frame + 100

            def get_priority(self):
                return 50

        proc = MyProcessor()
        clean_registry.register(FramePreProcessor, proc)

        # Desactivar
        clean_registry.disable(FramePreProcessor, proc)

        frame = np.array([[1]], dtype=np.int32)
        result = api.apply_pre_processors(0, frame)

        assert result[0][0] == 1  # No modificado

    def test_register_via_api_then_disable_via_registry(self, clean_registry):
        """Registrar vía API, desactivar vía registry."""
        api = FramesAPIImpl()

        api.register_pre_processor(
            lambda cid, f: f + 100,
            priority=50,
        )

        # Obtener el adapter
        processors = clean_registry.get(FramePreProcessor)
        assert len(processors) == 1

        # Desactivar
        clean_registry.disable(FramePreProcessor, processors[0])

        frame = np.array([[1]], dtype=np.int32)
        result = api.apply_pre_processors(0, frame)

        # No debe haberse aplicado
        assert result[0][0] == 1

    def test_fallback_without_registry(self, monkeypatch):
        """Sin registry, FramesAPIImpl debe seguir funcionando."""
        # Simular que get_extension_registry retorna None
        import core.extension_registry as er
        monkeypatch.setattr(er, "_registry", None)

        api = FramesAPIImpl()

        def processor(cid, f):
            return f + 5

        api.register_pre_processor(processor)

        frame = np.array([[1]], dtype=np.int32)
        result = api.apply_pre_processors(0, frame)

        # Debe haber usado el fallback local
        assert result[0][0] == 6


class TestCamerasAPIRegistryIntegration:

    def test_register_frame_processor(self, clean_registry):
        """CamerasAPIImpl debe registrar en el registry."""
        api = CamerasAPIImpl()
        api.register_frame_processor(lambda cid, f: f + 1)

        processors = clean_registry.get(FramePreProcessor)
        assert len(processors) == 1

    def test_process_frame(self, clean_registry):
        """process_frame debe aplicar processors del registry."""
        api = CamerasAPIImpl()
        api.register_frame_processor(lambda cid, f: f * 3)

        frame = np.array([[2]], dtype=np.int32)
        result = api.process_frame(0, frame)

        assert result[0][0] == 6