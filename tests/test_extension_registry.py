"""Tests para core/extension_registry.py"""
import pytest
from core.extension_registry import (
    ExtensionRegistry,
    get_extension_registry,
    set_extension_registry,
)


# Interfaz de prueba
class TestInterface:
    def do_something(self):
        return "test"


class ImplA:
    def do_something(self):
        return "A"


class ImplB:
    def do_something(self):
        return "B"


class TestExtensionRegistryBasic:
    def test_register_and_get(self):
        registry = ExtensionRegistry()
        a = ImplA()
        registry.register(TestInterface, a)

        result = registry.get(TestInterface)
        assert len(result) == 1
        assert result[0] is a

    def test_register_multiple(self):
        registry = ExtensionRegistry()
        a = ImplA()
        b = ImplB()
        registry.register(TestInterface, a)
        registry.register(TestInterface, b)

        result = registry.get(TestInterface)
        assert len(result) == 2

    def test_priority_order(self):
        registry = ExtensionRegistry()
        a = ImplA()
        b = ImplB()
        registry.register(TestInterface, a, priority=100)
        registry.register(TestInterface, b, priority=10)

        result = registry.get(TestInterface)
        assert result[0] is b   # b tiene prioridad 10
        assert result[1] is a   # a tiene prioridad 100

    def test_get_one(self):
        registry = ExtensionRegistry()
        a = ImplA()
        b = ImplB()
        registry.register(TestInterface, a, priority=100)
        registry.register(TestInterface, b, priority=10)

        assert registry.get_one(TestInterface) is b

    def test_get_one_empty(self):
        registry = ExtensionRegistry()
        assert registry.get_one(TestInterface) is None

    def test_has(self):
        registry = ExtensionRegistry()
        assert not registry.has(TestInterface)

        registry.register(TestInterface, ImplA())
        assert registry.has(TestInterface)

    def test_count(self):
        registry = ExtensionRegistry()
        assert registry.count(TestInterface) == 0

        registry.register(TestInterface, ImplA())
        registry.register(TestInterface, ImplB())
        assert registry.count(TestInterface) == 2


class TestExtensionRegistryUnregister:
    def test_unregister_one(self):
        registry = ExtensionRegistry()
        a = ImplA()
        b = ImplB()
        registry.register(TestInterface, a)
        registry.register(TestInterface, b)

        registry.unregister(TestInterface, a)
        result = registry.get(TestInterface)
        assert len(result) == 1
        assert result[0] is b

    def test_unregister_all_from_owner(self):
        registry = ExtensionRegistry()
        registry.register(TestInterface, ImplA(), owner="plugin_x")
        registry.register(TestInterface, ImplB(), owner="plugin_x")

        registry.unregister_all_from("plugin_x")
        assert registry.count(TestInterface) == 0

    def test_unregister_nonexistent(self):
        registry = ExtensionRegistry()
        registry.unregister(TestInterface, ImplA())  # No debe crashear


class TestExtensionRegistryEnable:
    def test_disable_enable(self):
        registry = ExtensionRegistry()
        a = ImplA()
        registry.register(TestInterface, a)

        registry.disable(TestInterface, a)
        assert registry.count(TestInterface) == 0
        assert len(registry.get_all(TestInterface)) == 1

        registry.enable(TestInterface, a)
        assert registry.count(TestInterface) == 1


class TestExtensionRegistryInterceptors:
    def test_interceptor_filters(self):
        registry = ExtensionRegistry()
        a = ImplA()
        b = ImplB()
        registry.register(TestInterface, a)
        registry.register(TestInterface, b)

        def filter_interceptor(implementations):
            return [i for i in implementations if isinstance(i, ImplA)]

        registry.intercept(TestInterface, filter_interceptor)

        result = registry.get(TestInterface)
        assert len(result) == 1
        assert result[0] is a


class TestExtensionRegistryStats:
    def test_stats(self):
        registry = ExtensionRegistry()
        registry.register(TestInterface, ImplA())
        registry.register(TestInterface, ImplB())

        stats = registry.get_stats()
        assert stats["total_registrations"] == 2
        assert "TestInterface" in stats["by_interface"]


class TestExtensionRegistrySingleton:
    def test_singleton(self):
        r1 = get_extension_registry()
        r2 = get_extension_registry()
        assert r1 is r2

    def test_set_extension_registry(self):
        custom = ExtensionRegistry()
        set_extension_registry(custom)
        assert get_extension_registry() is custom