"""
Sistema de hooks para comunicación entre plugins.

Los plugins pueden:
- REGISTRAR callbacks para un hook (con prioridad)
- EMITIR un hook para que todos los callbacks reaccionen

Ejemplo:
    # Plugin A registra
    self.register_hook("frame_processed", self.on_frame, priority=50)

    # Plugin B emite
    self.emit("frame_processed", camera_id=0, frame=img)
"""
import threading
from typing import Callable, Dict, List, Any, Optional
from dataclasses import dataclass, field

from utils.logger import get_logger

logger = get_logger("HookRegistry")


@dataclass
class HookSubscriber:
    """Un suscriptor a un hook."""
    callback: Callable
    priority: int = 50          # Menor = se ejecuta primero
    owner: str = ""             # Nombre del plugin dueño
    order: int = 0              # Orden de registro (para estabilidad)


class HookRegistry:
    """
    Registro centralizado de hooks.

    Los hooks permiten comunicación desacoplada entre plugins.
    """

    def __init__(self):
        self._hooks: Dict[str, List[HookSubscriber]] = {}
        self._lock = threading.RLock()
        self._counter = 0

        # Estadísticas
        self._emit_count: Dict[str, int] = {}
        self._error_count: Dict[str, int] = {}

    # ==================== REGISTRO ====================

    def register(
        self,
        hook_name: str,
        callback: Callable,
        priority: int = 50,
        owner: str = "",
    ):
        """
        Registra un callback para un hook.

        Args:
            hook_name: Nombre del hook (ej. "frame_processed")
            callback: Función a llamar cuando se emita el hook
            priority: Menor número = se ejecuta antes
            owner: Nombre del plugin (para debugging)
        """
        if not callable(callback):
            logger.error(f"❌ [{hook_name}] callback no es callable: {callback}")
            return

        with self._lock:
            if hook_name not in self._hooks:
                self._hooks[hook_name] = []

            self._counter += 1
            subscriber = HookSubscriber(
                callback=callback,
                priority=priority,
                owner=owner,
                order=self._counter,
            )

            self._hooks[hook_name].append(subscriber)

            # Ordenar por prioridad, luego por orden de registro
            self._hooks[hook_name].sort(
                key=lambda s: (s.priority, s.order)
            )

        logger.debug(
            f"🔗 [hooks] '{hook_name}' ← {owner or 'anonymous'} "
            f"(prio={priority}, total={len(self._hooks[hook_name])})"
        )

    def unregister(self, hook_name: str, callback: Callable):
        """Desregistra un callback de un hook."""
        with self._lock:
            if hook_name not in self._hooks:
                return

            before = len(self._hooks[hook_name])
            self._hooks[hook_name] = [
                s for s in self._hooks[hook_name]
                if s.callback is not callback
            ]
            after = len(self._hooks[hook_name])

            if before != after:
                logger.debug(
                    f"🔗 [hooks] '{hook_name}' ← removido "
                    f"({before} → {after})"
                )

    def unregister_all_from(self, owner: str):
        """Desregistra TODOS los hooks de un plugin."""
        with self._lock:
            removed = 0
            for hook_name in list(self._hooks.keys()):
                before = len(self._hooks[hook_name])
                self._hooks[hook_name] = [
                    s for s in self._hooks[hook_name]
                    if s.owner != owner
                ]
                after = len(self._hooks[hook_name])
                removed += (before - after)

                if not self._hooks[hook_name]:
                    del self._hooks[hook_name]

            if removed > 0:
                logger.debug(
                    f"🔗 [hooks] Removidos {removed} hooks de '{owner}'"
                )

    # ==================== EMISIÓN ====================

    def emit(self, hook_name: str, **kwargs) -> List[Any]:
        """
        Emite un hook.

        Args:
            hook_name: Nombre del hook
            **kwargs: Argumentos que recibirán los callbacks

        Returns:
            Lista de resultados (None si el callback no retorna nada)
        """
        with self._lock:
            subscribers = list(self._hooks.get(hook_name, []))

        if not subscribers:
            logger.debug(f"🔗 [hooks] '{hook_name}' sin suscriptores")
            return []

        self._emit_count[hook_name] = self._emit_count.get(hook_name, 0) + 1

        results = []
        for subscriber in subscribers:
            try:
                result = subscriber.callback(**kwargs)
                results.append(result)
            except Exception as e:
                self._error_count[hook_name] = self._error_count.get(hook_name, 0) + 1
                logger.error(
                    f"❌ [hooks] '{hook_name}' callback de "
                    f"'{subscriber.owner}' falló: {type(e).__name__}: {e}",
                    exc_info=True,
                )
                results.append(None)

        return results

    def emit_chain(self, hook_name: str, value: Any, **kwargs) -> Any:
        """
        Emite un hook en CADENA.

        Cada callback recibe el resultado del anterior y puede modificarlo.
        Útil para procesamiento de frames.

        Args:
            hook_name: Nombre del hook
            value: Valor inicial que se pasa y transforma
            **kwargs: Argumentos extra para los callbacks

        Returns:
            El valor transformado por todos los callbacks
        """
        with self._lock:
            subscribers = list(self._hooks.get(hook_name, []))

        current = value
        for subscriber in subscribers:
            try:
                result = subscriber.callback(value=current, **kwargs)
                if result is not None:
                    current = result
            except Exception as e:
                logger.error(
                    f"❌ [hooks] '{hook_name}' (chain) callback de "
                    f"'{subscriber.owner}' falló: {type(e).__name__}: {e}",
                    exc_info=True,
                )

        return current

    # ==================== CONSULTAS ====================

    def list_hooks(self) -> List[str]:
        """Lista todos los hooks registrados."""
        with self._lock:
            return list(self._hooks.keys())

    def get_subscriber_count(self, hook_name: str) -> int:
        """Retorna cuántos suscriptores tiene un hook."""
        with self._lock:
            return len(self._hooks.get(hook_name, []))

    def get_stats(self) -> Dict[str, Dict]:
        """Retorna estadísticas de uso."""
        with self._lock:
            stats = {}
            for hook_name in self._hooks.keys():
                stats[hook_name] = {
                    "subscribers": len(self._hooks[hook_name]),
                    "emits": self._emit_count.get(hook_name, 0),
                    "errors": self._error_count.get(hook_name, 0),
                }
            return stats

    def clear(self):
        """Limpia todos los hooks."""
        with self._lock:
            self._hooks.clear()
            self._emit_count.clear()
            self._error_count.clear()
        logger.debug("🔗 [hooks] Registry limpiado")


# ==================== SINGLETON ====================

_hook_registry: Optional[HookRegistry] = None
_registry_lock = threading.Lock()


def get_hook_registry() -> HookRegistry:
    """Obtiene (o crea) el registro global de hooks."""
    global _hook_registry

    with _registry_lock:
        if _hook_registry is None:
            _hook_registry = HookRegistry()
            logger.debug("🔗 [hooks] Registry global creado")

    return _hook_registry


# ==================== HOOK NAMES (CONSTANTES) ====================

class Hooks:
    """
    Nombres de hooks estándar.

    Los plugins pueden usar estos hooks o crear los suyos propios.
    """

    # === Ciclo de vida de la app ===
    APP_STARTING = "app_starting"
    APP_STARTED = "app_started"
    APP_CLOSING = "app_closing"
    APP_CLOSED = "app_closed"

    # === Ciclo de vida de cámaras ===
    CAMERA_ADDED = "camera_added"
    CAMERA_REMOVED = "camera_removed"
    CAMERA_CONNECTED = "camera_connected"
    CAMERA_DISCONNECTED = "camera_disconnected"
    CAMERA_ERROR = "camera_error"

    # === Frames ===
    FRAME_RECEIVED = "frame_received"          # Se recibe un frame nuevo
    FRAME_PROCESSING = "frame_processing"      # Chain: modificar frame
    FRAME_READY = "frame_ready"                # Frame listo para mostrar

    # === Detecciones ===
    MOTION_DETECTED = "motion_detected"
    FACE_DETECTED = "face_detected"
    DOCUMENT_DETECTED = "document_detected"
    TEXT_RECOGNIZED = "text_recognized"

    # === Grabación ===
    RECORDING_STARTED = "recording_started"
    RECORDING_STOPPED = "recording_stopped"

    # === Captura ===
    IMAGE_CAPTURED = "image_captured"
    IMAGE_SAVED = "image_saved"

    # === Configuración ===
    SETTINGS_CHANGED = "settings_changed"
    PLUGIN_ENABLED = "plugin_enabled"
    PLUGIN_DISABLED = "plugin_disabled"