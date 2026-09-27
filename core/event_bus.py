"""
Event bus del Core.

Los componentes del Core emiten eventos del dominio (genéricos).
Los plugins (o el propio Core) se suscriben a ellos.

NO conoce ningún evento específico. Cualquiera puede emitir cualquier cosa.
NO importa de plugins. Es infraestructura pura del Core.

Uso:
    from core.event_bus import get_event_bus
    from core.events import MOTION_DETECTED

    # Emitir
    get_event_bus().emit(MOTION_DETECTED, camera_id=0, rects=[...])

    # Suscribirse (en un plugin)
    get_event_bus().subscribe(MOTION_DETECTED, self._on_motion, owner=self.NAME)
"""
import threading
from typing import Callable, Dict, List

from utils.logger import get_logger

logger = get_logger("EventBus")


class EventBus:
    """
    Bus de eventos síncrono, thread-safe.

    El emisor recorre la lista de suscriptores y llama a cada uno.
    Si un suscriptor falla, se loggea y se continúa con el resto
    (un plugin roto no debe tumbar al Core).
    """

    def __init__(self):
        self._subs: Dict[str, List[Callable]] = {}
        self._owners: Dict[str, List[str]] = {}   # evento → [owner, ...]
        self._lock = threading.RLock()

    # ==================== SUSCRIPCIÓN ====================

    def subscribe(self, event: str, callback: Callable, owner: str = "") -> None:
        """
        Suscribe un callback a un evento.

        Args:
            event: nombre del evento (de core.events)
            callback: función a llamar cuando se emita
            owner: quién se suscribe (para cleanup automático)
        """
        if not callable(callback):
            logger.error(f"❌ Suscriptor no callable para '{event}': {callback}")
            return

        with self._lock:
            self._subs.setdefault(event, []).append(callback)
            self._owners.setdefault(event, []).append(owner)

        logger.debug(f"🔗 [bus] '{event}' ← {owner or 'anonymous'}")

    def unsubscribe(self, event: str, callback: Callable) -> None:
        """Desuscribe un callback específico."""
        with self._lock:
            if event not in self._subs:
                return
            subs = self._subs[event]
            owners = self._owners[event]
            for i, cb in enumerate(subs):
                if cb is callback:
                    subs.pop(i)
                    owners.pop(i)
                    break

    def unsubscribe_all_from(self, owner: str) -> None:
        """Desuscribe TODOS los callbacks de un owner (para on_disable de plugins)."""
        with self._lock:
            removed = 0
            for event in list(self._subs.keys()):
                subs = self._subs[event]
                owners = self._owners[event]
                keep = [(cb, ow) for cb, ow in zip(subs, owners) if ow != owner]
                removed += len(subs) - len(keep)
                if keep:
                    self._subs[event] = [cb for cb, _ in keep]
                    self._owners[event] = [ow for _, ow in keep]
                else:
                    del self._subs[event]
                    self._owners.pop(event, None)

        if removed:
            logger.debug(f"🔗 [bus] Removidos {removed} suscriptores de '{owner}'")

    # ==================== EMISIÓN ====================

    def emit(self, event: str, **kwargs) -> int:
        """
        Emite un evento. Llama a todos los suscriptores en orden de suscripción.

        Args:
            event: nombre del evento
            **kwargs: argumentos que reciben los callbacks

        Returns:
            Número de suscriptores que recibieron el evento sin error.
        """
        with self._lock:
            subs = list(self._subs.get(event, []))

        if not subs:
            logger.debug(f"🔗 [bus] '{event}' sin suscriptores")
            return 0

        ok = 0
        for cb in subs:
            try:
                cb(**kwargs)
                ok += 1
            except Exception as e:
                logger.error(
                    f"❌ [bus] Error en suscriptor de '{event}': "
                    f"{type(e).__name__}: {e}",
                    exc_info=True,
                )

        return ok

    # ==================== CONSULTAS ====================

    def list_events(self) -> List[str]:
        """Lista eventos con suscriptores."""
        with self._lock:
            return list(self._subs.keys())

    def count_subscribers(self, event: str) -> int:
        """Cuenta suscriptores de un evento."""
        with self._lock:
            return len(self._subs.get(event, []))

    def clear(self) -> None:
        """Limpia todos los suscriptores (para tests)."""
        with self._lock:
            self._subs.clear()
            self._owners.clear()


# ==================== SINGLETON ====================

_bus = None
_lock = threading.Lock()


def get_event_bus() -> EventBus:
    """Obtiene el bus global."""
    global _bus
    with _lock:
        if _bus is None:
            _bus = EventBus()
    return _bus


def set_event_bus(bus: EventBus) -> None:
    """Reemplaza el bus global (para tests)."""
    global _bus
    with _lock:
        _bus = bus