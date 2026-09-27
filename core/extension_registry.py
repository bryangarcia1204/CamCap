"""
Registro central de extensiones.

A diferencia del PluginManager, NO conoce plugins.
Solo conoce TIPOS de extensiones (interfaces).

Cualquier código (plugins, código builtin, tests) puede:
- Registrar implementaciones de interfaces
- Consultar implementaciones por interfaz
- Interceptar/middleware sobre extensiones
"""
import threading
from typing import Type, TypeVar, List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field

from utils.logger import get_logger

logger = get_logger("ExtensionRegistry")

T = TypeVar('T')


@dataclass
class ExtensionEntry:
    """Una implementación registrada de una interfaz."""
    implementation: Any
    priority: int = 50              # Menor = se ejecuta primero
    owner: str = ""                 # Quién la registró (plugin name o "builtin")
    order: int = 0                  # Orden de registro
    enabled: bool = True            # Se puede desactivar sin eliminar
    metadata: Dict[str, Any] = field(default_factory=dict)


class ExtensionRegistry:
    """
    Registro central de extensiones.

    Uso:
        registry = ExtensionRegistry()
        registry.register(CameraProvider, MyCameraProvider(), priority=50)
        providers = registry.get(CameraProvider)
        for p in providers:
            p.get_stream_url(camera)
    """

    def __init__(self):
        self._extensions: Dict[Type, List[ExtensionEntry]] = {}
        self._lock = threading.RLock()
        self._counter = 0

        # Estadísticas
        self._stats = {
            "total_registrations": 0,
            "total_queries": 0,
        }

        logger.info("📦 ExtensionRegistry inicializado")

    # ==================== REGISTRO ====================

    def register(
        self,
        interface: Type,
        implementation: Any,
        priority: int = 50,
        owner: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Registra una implementación de una interfaz.

        Args:
            interface: El tipo de interfaz (ej. CameraProvider)
            implementation: La instancia que la implementa
            priority: Orden (menor = primero)
            owner: Nombre del registrador (plugin o "builtin")
            metadata: Datos extra opcionales
        """
        if implementation is None:
            logger.error(f"❌ [registry] Implementación None para {interface.__name__}")
            return

        with self._lock:
            if interface not in self._extensions:
                self._extensions[interface] = []

            self._counter += 1
            entry = ExtensionEntry(
                implementation=implementation,
                priority=priority,
                owner=owner,
                order=self._counter,
                metadata=metadata or {},
            )

            self._extensions[interface].append(entry)

            # Ordenar por prioridad, luego por orden de registro
            self._extensions[interface].sort(
                key=lambda e: (e.priority, e.order)
            )

            self._stats["total_registrations"] += 1

        logger.debug(
            f"📦 [registry] {interface.__name__} ← "
            f"'{owner or 'anonymous'}' (prio={priority})"
        )

    def unregister(self, interface: Type, implementation: Any):
        """Desregistra una implementación específica."""
        with self._lock:
            if interface not in self._extensions:
                return

            before = len(self._extensions[interface])
            self._extensions[interface] = [
                e for e in self._extensions[interface]
                if e.implementation is not implementation
            ]
            after = len(self._extensions[interface])

            if before != after:
                logger.debug(
                    f"📦 [registry] {interface.__name__} removido "
                    f"({before} → {after})"
                )

    def unregister_all_from(self, owner: str):
        """Desregistra TODAS las extensiones de un owner (plugin)."""
        with self._lock:
            removed = 0
            for interface in list(self._extensions.keys()):
                before = len(self._extensions[interface])
                self._extensions[interface] = [
                    e for e in self._extensions[interface]
                    if e.owner != owner
                ]
                after = len(self._extensions[interface])
                removed += (before - after)

                if not self._extensions[interface]:
                    del self._extensions[interface]

        if removed > 0:
            logger.debug(
                f"📦 [registry] Removidas {removed} extensiones de '{owner}'"
            )

    # ==================== CONSULTA ====================

    def get(self, interface: Type[T]) -> List[T]:
        """
        Retorna todas las implementaciones activas de una interfaz,
        ordenadas por prioridad.

        Aplica todos los interceptores registrados para esta interfaz.

        Uso:
            providers = registry.get(CameraProvider)
            for p in providers:
                if p.can_handle(camera):
                    url = p.get_stream_url(camera)
        """
        with self._lock:
            entries = self._extensions.get(interface, [])
            result = [
                e.implementation for e in entries if e.enabled
            ]
            self._stats["total_queries"] += 1

        # ✅ Aplicar interceptores FUERA del lock
        result = self._apply_interceptors(interface, result)

        return result

    def get_all(self, interface: Type[T]) -> List[T]:
        """Como get() pero incluye desactivadas."""
        with self._lock:
            entries = self._extensions.get(interface, [])
            return [e.implementation for e in entries]

    def get_one(self, interface: Type[T]) -> Optional[T]:
        """
        Retorna la primera implementación (mayor prioridad).

        Aplica interceptores primero.
        """
        implementations = self.get(interface)
        return implementations[0] if implementations else None

    def has(self, interface: Type) -> bool:
        """Verifica si hay alguna implementación registrada."""
        with self._lock:
            entries = self._extensions.get(interface, [])
            return any(e.enabled for e in entries)

    def count(self, interface: Type) -> int:
        """Cuenta implementaciones activas."""
        with self._lock:
            entries = self._extensions.get(interface, [])
            return sum(1 for e in entries if e.enabled)

    def list_interfaces(self) -> List[Type]:
        """Lista todas las interfaces con implementaciones registradas."""
        with self._lock:
            return [
                iface for iface, entries in self._extensions.items()
                if entries
            ]

    # ==================== ACTIVACIÓN/DESACTIVACIÓN ====================

    def enable(self, interface: Type, implementation: Any):
        """Activa una implementación sin eliminarla."""
        self._set_enabled(interface, implementation, True)

    def disable(self, interface: Type, implementation: Any):
        """Desactiva una implementación sin eliminarla."""
        self._set_enabled(interface, implementation, False)

    def _set_enabled(self, interface: Type, implementation: Any, enabled: bool):
        with self._lock:
            entries = self._extensions.get(interface, [])
            for entry in entries:
                if entry.implementation is implementation:
                    entry.enabled = enabled
                    return

    # ==================== MIDDLEWARE ====================

    def intercept(
        self,
        interface: Type,
        callback: Callable,
        priority: int = 50,
        owner: str = "",
    ):
        """
        Registra un interceptor para una interfaz.

        El callback se llama ANTES de retornar las implementaciones.
        Puede modificar la lista.

        Uso:
            def filter_cameras(implementations):
                return [i for i in implementations if i.is_valid()]
            registry.intercept(CameraProvider, filter_cameras)
        """
        # Los interceptores se guardan en un dict separado
        if not hasattr(self, '_interceptors'):
            self._interceptors: Dict[Type, List[ExtensionEntry]] = {}

        with self._lock:
            if interface not in self._interceptors:
                self._interceptors[interface] = []

            self._counter += 1
            entry = ExtensionEntry(
                implementation=callback,
                priority=priority,
                owner=owner,
                order=self._counter,
            )
            self._interceptors[interface].append(entry)
            self._interceptors[interface].sort(
                key=lambda e: (e.priority, e.order)
            )

        logger.debug(
            f"📦 [registry] Interceptor para {interface.__name__} ← '{owner}'"
        )

    def _apply_interceptors(self, interface: Type, implementations: List) -> List:
        """Aplica todos los interceptores registrados para una interfaz."""
        if not hasattr(self, '_interceptors'):
            return implementations

        interceptors = self._interceptors.get(interface, [])
        result = implementations
        for interceptor in interceptors:
            try:
                new_result = interceptor.implementation(result)
                if new_result is not None:
                    result = new_result
            except Exception as e:
                logger.error(
                    f"❌ Interceptor de {interface.__name__} falló: {e}",
                    exc_info=True,
                )
        return result

    # ==================== ESTADÍSTICAS ====================

    def get_stats(self) -> Dict[str, Any]:
        """Estadísticas del registro."""
        with self._lock:
            by_interface = {}
            for interface, entries in self._extensions.items():
                by_interface[interface.__name__] = {
                    "total": len(entries),
                    "enabled": sum(1 for e in entries if e.enabled),
                }

            return {
                **self._stats,
                "total_interfaces": len(self._extensions),
                "by_interface": by_interface,
            }

    def clear(self):
        """Limpia TODO el registro."""
        with self._lock:
            self._extensions.clear()
            if hasattr(self, '_interceptors'):
                self._interceptors.clear()
            self._stats = {"total_registrations": 0, "total_queries": 0}
        logger.debug("📦 [registry] Limpiado")

    def __repr__(self) -> str:
        return f"<ExtensionRegistry interfaces={len(self._extensions)}>"


# ==================== SINGLETON ====================

_registry: Optional[ExtensionRegistry] = None
_registry_lock = threading.Lock()


def get_extension_registry() -> ExtensionRegistry:
    """Obtiene (o crea) el registro global."""
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = ExtensionRegistry()
    return _registry


def set_extension_registry(registry: ExtensionRegistry):
    """Registra un registry global (para tests)."""
    global _registry
    with _registry_lock:
        _registry = registry