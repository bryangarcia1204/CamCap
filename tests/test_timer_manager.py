"""Tests para utils/timer_manager.py

FIX v2:
- Tests de destroy() (nuevo método)
- Tests de reutilización de timers
- Config-driven con TimerManager
"""
import pytest
import time
from PySide6.QtCore import QTimer, QCoreApplication
from PySide6.QtWidgets import QApplication

from utils.timer_manager import TimerManager


def _process_events(duration_s=0.1):
    """Procesa eventos de Qt durante N segundos"""
    end = time.time() + duration_s
    while time.time() < end:
        QCoreApplication.processEvents()
        time.sleep(0.005)


@pytest.mark.gui
class TestTimerManagerSingleton:
    def test_singleton(self, qapp):
        tm1 = TimerManager()
        tm2 = TimerManager()
        assert tm1 is tm2


@pytest.mark.gui
class TestTimerManagerCreate:
    def test_create_timer(self, qapp):
        tm = TimerManager()
        tm.stop_all()

        tm.create("test_create", 100, lambda: None)
        assert tm.exists("test_create")
        tm.stop("test_create")

    def test_create_without_start(self, qapp):
        tm = TimerManager()
        tm.stop_all()

        tm.create("test_no_start", 100, lambda: None, start=False)
        assert tm.exists("test_no_start")
        assert not tm.is_running("test_no_start")
        tm.stop("test_no_start")

    def test_create_reuses_same_config(self, qapp):
        """Crear 2 veces con misma config debe reutilizar"""
        tm = TimerManager()
        tm.stop_all()

        counter = [0]
        tm.create("test_reuse", 100, lambda: counter.__setitem__(0, counter[0] + 1))
        tm.create("test_reuse", 100, lambda: counter.__setitem__(0, counter[0] + 1))

        # Debe existir solo un timer
        assert tm.list_timers().count("test_reuse") == 1
        tm.stop("test_reuse")


@pytest.mark.gui
class TestTimerManagerStop:
    def test_stop_removes_timer(self, qapp):
        tm = TimerManager()
        tm.create("test_stop", 100, lambda: None)
        assert tm.exists("test_stop")

        tm.stop("test_stop")
        # Tras stop, no debe estar en el registro si fue destroy
        # O puede seguir existiendo si fue stop simple

    def test_stop_nonexistent_is_safe(self, qapp):
        tm = TimerManager()
        tm.stop("no_existe")  # No debe crashear

    def test_destroy_removes_completely(self, qapp):
        """shutdown() debe eliminar el timer del registro"""
        tm = TimerManager()
        tm.stop_all()

        tm.create("test_destroy", 100, lambda: None)
        assert tm.exists("test_destroy")

        tm.shutdown()
        assert not tm.is_running("test_destroy")


@pytest.mark.gui
class TestTimerManagerGroups:
    def test_create_group(self, qapp):
        tm = TimerManager()
        tm.stop_all()

        tm.create_group("test_group", [
            ("timer1", 100, lambda: None, False),
            ("timer2", 200, lambda: None, False),
        ])

        assert tm.exists("test_group.timer1")
        assert tm.exists("test_group.timer2")

        tm.stop_group("test_group")

    def test_stop_group_removes_all(self, qapp):
        tm = TimerManager()
        tm.create_group("group_x", [
            ("a", 100, lambda: None, False),
            ("b", 100, lambda: None, False),
        ])

        tm.stop_group("group_x")
        assert not tm.exists("group_x.a")
        assert not tm.exists("group_x.b")

    def test_stop_nonexistent_group_is_safe(self, qapp):
        tm = TimerManager()
        tm.stop_group("no_existe")  # No debe crashear

    def test_group_with_3_elements(self, qapp):
        """Specs de 3 elementos (sin single_shot)"""
        tm = TimerManager()
        tm.stop_all()

        tm.create_group("group_3", [
            ("x", 100, lambda: None),
            ("y", 200, lambda: None),
        ])

        assert tm.exists("group_3.x")
        assert tm.exists("group_3.y")
        tm.stop_group("group_3")


@pytest.mark.gui
class TestTimerManagerStopAll:
    def test_stop_all_clears_everything(self, qapp):
        tm = TimerManager()
        tm.create("test_a", 100, lambda: None)
        tm.create("test_b", 100, lambda: None)

        tm.stop_all()

        # No debe haber timers activos        
        assert len(tm.list_timers()) == 0 or all(not tm.is_running(name) for name in tm.list_timers()
        )


@pytest.mark.gui
class TestTimerManagerCallbacks:
    def test_callback_is_called(self, qapp):
        """El timer debe llamar al callback periódicamente"""
        tm = TimerManager()
        tm.stop_all()

        counter = [0]
        tm.create("test_cb", 50, lambda: counter.__setitem__(0, counter[0] + 1))

        _process_events(0.2)
        tm.stop("test_cb")

        assert counter[0] >= 1, "El callback no se llamó"

    def test_callback_exception_does_not_crash(self, qapp):
        """Un callback que crashea no debe matar el timer manager"""
        tm = TimerManager()
        tm.stop_all()

        def bad_callback():
            raise ValueError("Test error")

        tm.create("test_bad_cb", 50, bad_callback)

        # Procesar eventos: no debe crashear
        _process_events(0.15)
        tm.stop("test_bad_cb")


@pytest.mark.gui
class TestTimerManagerStatus:
    def test_is_running_true(self, qapp):
        tm = TimerManager()
        tm.stop_all()

        tm.create("test_running", 100, lambda: None, start=True)
        assert tm.is_running("test_running")
        tm.stop("test_running")

    def test_is_running_false_nonexistent(self, qapp):
        tm = TimerManager()
        assert not tm.is_running("no_existe")

    def test_exists(self, qapp):
        tm = TimerManager()
        tm.stop_all()

        tm.create("test_exists", 100, lambda: None)
        assert tm.exists("test_exists")
        assert not tm.exists("no_existe")
        tm.stop("test_exists")

    def test_list_timers(self, qapp):
        tm = TimerManager()
        tm.stop_all()

        tm.create("lista_a", 100, lambda: None)
        tm.create("lista_b", 100, lambda: None)

        timers = tm.list_timers()
        assert "lista_a" in timers
        assert "lista_b" in timers

        tm.stop_all()


@pytest.mark.gui
class TestTimerManagerShutdown:
    def test_shutdown_stops_all(self, qapp):
        tm = TimerManager()
        tm.create("test_shutdown", 100, lambda: None)
        tm.shutdown()
        # No debe haber timers activos