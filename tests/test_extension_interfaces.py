"""Tests para las interfaces de extensión."""
import pytest
import numpy as np

from core.extensions.interfaces import (
    CameraProvider,
    CameraDetector,
    FramePreProcessor,
    FramePostProcessor,
    ConfigTab,
    ThemeProvider,
    PluginWrapper,
)
from core.extensions.types import CameraProtocol, ThemeMode


class TestCameraProviderInterface:
    def test_structural_typing(self):
        """Un objeto con los métodos correctos debe satisfacer la interfaz."""
        class MyProvider:
            def can_handle(self, camera): return True
            def get_stream_url(self, camera): return "http://test"
            def get_protocol(self): return CameraProtocol.HTTP_MJPEG

        obj = MyProvider()
        assert isinstance(obj, CameraProvider)

    def test_missing_method_fails(self):
        class IncompleteProvider:
            def can_handle(self, camera): return True

        obj = IncompleteProvider()
        assert not isinstance(obj, CameraProvider)


class TestFramePreProcessorInterface:
    def test_structural_typing(self):
        class MyProcessor:
            def process(self, camera_id, frame): return frame
            def get_priority(self): return 50

        obj = MyProcessor()
        assert isinstance(obj, FramePreProcessor)


class TestConfigTabInterface:
    def test_structural_typing(self):
        class MyTab:
            def get_id(self): return "my_tab"
            def get_title(self): return "My Tab"
            def get_icon(self): return "🔧"
            def get_widget(self): return None
            def on_save(self): return True
            def on_load(self): pass

        obj = MyTab()
        assert isinstance(obj, ConfigTab)


class TestThemeProviderInterface:
    def test_structural_typing(self):
        class MyTheme:
            def get_id(self): return "dark"
            def get_name(self): return "Dark Theme"
            def get_mode(self): return ThemeMode.DARK
            def get_stylesheet(self): return "QWidget {}"
            def get_palette(self): return None

        obj = MyTheme()
        assert isinstance(obj, ThemeProvider)


class TestPluginWrapperInterface:
    def test_structural_typing(self):
        class MyWrapper:
            def wraps_plugin(self, name): return name == "target"
            def before_call(self, p, m, a, k): pass
            def after_call(self, p, m, r): return r
            def on_error(self, p, m, e): pass

        obj = MyWrapper()
        assert isinstance(obj, PluginWrapper)