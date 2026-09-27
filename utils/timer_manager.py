"""
Gestor centralizado de QTimer con soporte de grupos.
FIX: race condition en create_group/stop_group que causaba KeyError.
"""
import threading
from typing import Callable, Dict, List, Optional, Tuple
from PySide6.QtCore import QTimer, QObject, QCoreApplication, QThread

from utils.logger import get_logger

logger = get_logger("TimerManager")


class TimerManager(QObject):
    """Singleton que gestiona todos los QTimer de la aplicación."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, '_initialized', False):
            return
        super().__init__()
        self._initialized = True

        # Registro: nombre -> QTimer
        self._timers: Dict[str, QTimer] = {}
        # Callbacks por timer
        self._callbacks: Dict[str, Callable] = {}
        # Configuración por timer
        self._configs: Dict[str, dict] = {}
        # Grupos: owner -> lista de nombres
        self._groups: Dict[str, List[str]] = {}

        # Hilo GUI (diferido)
        self._gui_thread: Optional[threading.Thread] = None

        # Lock para operaciones críticas
        self._lock = threading.RLock()

        logger.info("⏱️ TimerManager inicializado")

    # ==================== HILO GUI ====================

    def _get_gui_thread(self) -> Optional[threading.Thread]:
        """
        Obtiene el hilo GUI de forma segura.

        Estrategia:
          1. Si ya lo capturamos antes, devolverlo.
          2. Si QApplication existe, su .thread() es el hilo GUI.
          3. Fallback: el hilo actual en la primera llamada.
        """
        if self._gui_thread is not None:
            return self._gui_thread

        app = QCoreApplication.instance()
        if app is not None:
            self._gui_thread = threading.current_thread()
            return self._gui_thread

        self._gui_thread = threading.current_thread()
        return self._gui_thread

    def _is_gui_thread(self) -> bool:
        """Verifica si estamos en el hilo GUI"""
        gui_thread = self._get_gui_thread()
        if gui_thread is None:
            return True

        current = threading.current_thread()

        if current is gui_thread:
            return True
        if current.ident == gui_thread.ident:
            return True

        try:
            qt_current = QThread.currentThread()
            qt_gui = QCoreApplication.instance().thread() if QCoreApplication.instance() else None
            if qt_gui is not None and qt_current is qt_gui:
                return True
        except Exception:
            pass

        return False

    def _assert_gui_thread(self, op: str, name: str = "") -> bool:
        """Verifica que estamos en el hilo GUI"""
        if self._is_gui_thread():
            return True

        current = threading.current_thread()
        logger.warning(
            f"⚠️ TimerManager.{op}('{name}') llamado desde hilo no-GUI "
            f"({current.name})"
        )
        return False

    # ==================== API PÚBLICA ====================

    def create(self, name: str, interval_ms: int, callback: Callable,
               single_shot: bool = False, start: bool = True) -> Optional[QTimer]:
        """Crea (o recrea) un QTimer gestionado."""
        if not self._assert_gui_thread("create", name):
            return None

        with self._lock:
            # Si ya existe, detenerlo primero
            if name in self._timers:
                self._stop_internal(name)

            def safe_callback():
                try:
                    callback()
                except Exception as e:
                    logger.error(
                        f"❌ [timer-cb] '{name}' callback lanzó excepción: "
                        f"{type(e).__name__}: {e}",
                        exc_info=True,
                    )

            try:
                timer = QTimer()
                timer.setInterval(interval_ms)
                timer.setSingleShot(single_shot)
                timer.timeout.connect(safe_callback)
            except Exception as e:
                logger.error(f"⏱️ Error creando timer '{name}': {e}")
                return None

            self._timers[name] = timer
            self._callbacks[name] = safe_callback
            self._configs[name] = {
                "interval_ms": interval_ms,
                "single_shot": single_shot,
            }

            if start:
                try:
                    timer.start()
                except Exception as e:
                    logger.error(f"⏱️ Error iniciando timer '{name}': {e}")

        logger.debug(f"⏱️ Timer '{name}' creado (interval={interval_ms}ms)")
        return timer

    def create_group(self, owner: str, specs: List[Tuple]):
        """
        Crea un grupo de timers bajo un mismo owner.

        FIX: race condition que causaba KeyError cuando otro flujo eliminaba
        el grupo mientras se estaba creando.
        """
        if not self._assert_gui_thread("create_group", owner):
            return

        with self._lock:
            # ✅ Crear/recrear el grupo de forma atómica
            # Si ya existe, lo reseteamos para evitar duplicados
            self._groups[owner] = []

            # ✅ Referencia local para evitar race conditions
            group_list = self._groups[owner]

        for spec in specs:
            if len(spec) == 4:
                short_name, interval, cb, single = spec
            elif len(spec) == 3:
                short_name, interval, cb = spec
                single = False
            else:
                logger.warning(f"⏱️ Spec inválida en grupo '{owner}': {spec}")
                continue

            full_name = f"{owner}.{short_name}"
            self.create(full_name, interval, cb, single)

            # ✅ Usar la referencia local con lock
            with self._lock:
                if owner in self._groups:
                    self._groups[owner].append(full_name)

        with self._lock:
            count = len(self._groups.get(owner, []))

        logger.debug(f"⏱️ Grupo '{owner}' creado con {count} timer(s)")

    def start(self, name: str, interval_ms: Optional[int] = None):
        if not self._assert_gui_thread("start", name):
            return
        timer = self._timers.get(name)
        if timer is None:
            logger.warning(f"⏱️ Timer '{name}' no existe")
            return
        try:
            if interval_ms is not None:
                timer.setInterval(interval_ms)
            timer.start()
            logger.debug(f"⏱️ Timer '{name}' iniciado")
        except Exception as e:
            logger.error(f"⏱️ Error iniciando timer '{name}': {e}")

    def stop(self, name: str):
        """Detiene y destruye un timer de forma segura"""
        if not self._assert_gui_thread("stop", name):
            pass

        with self._lock:
            self._stop_internal(name)

        logger.debug(f"⏱️ Timer '{name}' detenido")

    def _stop_internal(self, name: str):
        """Implementación interna de stop SIN lock (asume que ya se tiene)"""
        timer = self._timers.pop(name, None)
        if timer is None:
            return

        try:
            timer.stop()
        except Exception as e:
            logger.error(f"No se puedo detener y eliminar: {e}")

        # Desconectar el slot específico
        try:
            callback = self._callbacks.get(name)
            if callback is not None:
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", RuntimeWarning)
                    try:
                        timer.timeout.disconnect(callback)
                    except (RuntimeError, TypeError):
                        pass
        except Exception:
            pass

        try:
            timer.deleteLater()
        except Exception:
            pass

        self._callbacks.pop(name, None)
        self._configs.pop(name, None)

        # ✅ Eliminar de grupos con pop seguro
        for owner in list(self._groups.keys()):
            names = self._groups.get(owner)
            if names and name in names:
                names.remove(name)
                if not names:
                    self._groups.pop(owner, None)
        logger.debug(f"⏱️ Timer '{name}' detenido")

    def stop_group(self, owner: str):
        """Detiene todos los timers de un grupo"""
        with self._lock:
            names = self._groups.pop(owner, None)

        if not names:
            return

        logger.debug(f"⏱️ Deteniendo grupo '{owner}' ({len(names)} timer(s))")

        # ✅ Iterar sobre copia
        for name in list(names):
            with self._lock:
                self._stop_internal(name)

    def stop_all(self):
        """Detiene TODOS los timers"""
        with self._lock:
            names = list(self._timers.keys())

        logger.info(f"⏱️ Deteniendo {len(names)} timer(s)...")

        for name in names:
            with self._lock:
                self._stop_internal(name)

        with self._lock:
            self._groups.clear()

        logger.info("⏱️ Todos los timers detenidos")

    def is_running(self, name: str) -> bool:
        timer = self._timers.get(name)
        return timer is not None and timer.isActive()

    def exists(self, name: str) -> bool:
        return name in self._timers

    def list_timers(self) -> List[str]:
        return list(self._timers.keys())

    def list_groups(self) -> List[str]:
        return list(self._groups.keys())

    def shutdown(self):
        try:
            self.stop_all()
        except Exception as e:
            logger.debug(f"Error en shutdown de TimerManager: {e}")

    def destroy(self, name: str):
        """
        Alias de stop().

        Existe por compatibilidad con código que usa destroy().
        Detiene el timer y lo elimina del registro.
        """
        self.stop(name)


# Singleton global
timer_manager = TimerManager()