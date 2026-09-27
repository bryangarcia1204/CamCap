"""Tests para core/plugin_api/hooks.py"""
import pytest
from core.plugin_api.hooks import HookRegistry, get_hook_registry, Hooks


class TestHookRegistryBasic:
    def test_register_callback(self):
        registry = HookRegistry()
        called = []
        registry.register("test_hook", lambda: called.append(1))

        registry.emit("test_hook")
        assert called == [1]

    def test_register_multiple(self):
        registry = HookRegistry()
        called = []
        registry.register("test_hook", lambda: called.append("a"))
        registry.register("test_hook", lambda: called.append("b"))

        registry.emit("test_hook")
        assert len(called) == 2

    def test_unregister(self):
        registry = HookRegistry()
        called = []
        cb = lambda: called.append(1)

        registry.register("test_hook", cb)
        registry.unregister("test_hook", cb)
        registry.emit("test_hook")

        assert called == []

    def test_unregister_all_from(self):
        registry = HookRegistry()
        called = []

        registry.register("hook_a", lambda: called.append("a1"), owner="plugin_x")
        registry.register("hook_b", lambda: called.append("b1"), owner="plugin_x")
        registry.register("hook_a", lambda: called.append("a2"), owner="plugin_y")

        registry.unregister_all_from("plugin_x")
        registry.emit("hook_a")
        registry.emit("hook_b")

        assert called == ["a2"]


class TestHookRegistryPriority:
    def test_priority_order(self):
        registry = HookRegistry()
        called = []

        registry.register("test", lambda: called.append("low"), priority=100)
        registry.register("test", lambda: called.append("high"), priority=10)
        registry.register("test", lambda: called.append("mid"), priority=50)

        registry.emit("test")
        assert called == ["high", "mid", "low"]

    def test_same_priority_registration_order(self):
        registry = HookRegistry()
        called = []

        registry.register("test", lambda: called.append(1), priority=50)
        registry.register("test", lambda: called.append(2), priority=50)
        registry.register("test", lambda: called.append(3), priority=50)

        registry.emit("test")
        assert called == [1, 2, 3]


class TestHookRegistryArgs:
    def test_emit_with_kwargs(self):
        registry = HookRegistry()
        received = []

        def callback(camera_id, frame):
            received.append((camera_id, frame))

        registry.register("test", callback)
        registry.emit("test", camera_id=5, frame="test_frame")

        assert received == [(5, "test_frame")]

    def test_emit_chain(self):
        registry = HookRegistry()

        def add_one(value):
            return value + 1

        def multiply_two(value):
            return value * 2

        registry.register("chain", add_one, priority=10)
        registry.register("chain", multiply_two, priority=20)

        result = registry.emit_chain("chain", value=5)
        assert result == (5 + 1) * 2

    def test_emit_chain_none_result_keeps_value(self):
        registry = HookRegistry()

        def no_return(value):
            return None

        registry.register("chain", no_return)
        result = registry.emit_chain("chain", value=42)
        assert result == 42


class TestHookRegistryErrors:
    def test_callback_exception_isolated(self):
        registry = HookRegistry()
        called = []

        def bad_callback():
            raise ValueError("Test error")

        def good_callback():
            called.append(1)

        registry.register("test", bad_callback)
        registry.register("test", good_callback)

        # No debe crashear
        registry.emit("test")
        assert called == [1]

    def test_stats(self):
        registry = HookRegistry()
        registry.register("test", lambda: None)

        registry.emit("test")
        registry.emit("test")

        stats = registry.get_stats()
        assert stats["test"]["subscribers"] == 1
        assert stats["test"]["emits"] == 2


class TestHookRegistrySingleton:
    def test_singleton(self):
        r1 = get_hook_registry()
        r2 = get_hook_registry()
        assert r1 is r2


class TestHooksConstants:
    def test_constants_defined(self):
        assert Hooks.FRAME_RECEIVED == "frame_received"
        assert Hooks.CAMERA_ADDED == "camera_added"
        assert Hooks.MOTION_DETECTED == "motion_detected"