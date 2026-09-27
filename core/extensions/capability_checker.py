"""
CapabilityChecker — Verifica permisos de plugins en runtime.

Cada plugin declara en su manifest.json qué capabilities necesita.
Antes de dar acceso a un recurso, se verifica que el plugin lo declaró.

Uso:
    checker = get_capability_checker()
    if not checker.check("telegram_notifier", Capability.NETWORK):
        raise PermissionError("network not granted")
"""
import threading
from typing import Dict, Set, Optional, List
from utils.logger import get_logger

logger = get_logger("CapabilityChecker")


class CapabilityChecker:
    """Singleton que verifica capabilities."""

    def __init__(self):
        self._capabilities: Dict[str, Set] = {}
        self._lock = threading.RLock()
        self._strict_mode = True   # False → permite todo (para desarrollo)
        self._denials: List[Dict] = []   # historial de denegaciones

        logger.info("🔒 CapabilityChecker inicializado")

    def register_plugin(self, plugin_name: str, capabilities: List[str]):
        """
        Registra las capabilities declaradas por un plugin.

        Args:
            plugin_name: nombre único del plugin
            capabilities: lista de strings (ej. ["network", "write_files"])
        """
        with self._lock:
            caps_set = set()
            from .types import Capability

            for cap_str in capabilities:
                try:
                    cap = Capability(cap_str)
                    caps_set.add(cap)
                except ValueError:
                    logger.warning(
                        f"⚠️ Capability desconocida '{cap_str}' en plugin "
                        f"'{plugin_name}'"
                    )

            self._capabilities[plugin_name] = caps_set

            if caps_set:
                cap_names = sorted(c.value for c in caps_set)
                logger.info(
                    f"🔒 Plugin '{plugin_name}': capabilities = {cap_names}"
                )
            else:
                logger.info(f"🔒 Plugin '{plugin_name}': sin capabilities")

    def check(self, plugin_name: str, capability) -> bool:
        """
        Verifica si un plugin tiene una capability.

        Args:
            plugin_name: nombre del plugin
            capability: Capability enum

        Returns:
            True si tiene permiso, False si no.
        """
        from .types import Capability

        if not isinstance(capability, Capability):
            logger.warning(
                f"⚠️ check() con capability inválida: {capability}"
            )
            return False

        # Modo no estricto (desarrollo): permitir todo
        if not self._strict_mode:
            return True

        # Plugins builtin no declaran capabilities (confianza total)
        if plugin_name in ("builtin", "core", ""):
            return True

        with self._lock:
            caps = self._capabilities.get(plugin_name)

        if caps is None:
            # Plugin no registrado → denegar por seguridad
            self._log_denial(plugin_name, capability, "plugin no registrado")
            return False

        if capability in caps:
            return True

        self._log_denial(plugin_name, capability, "capability no declarada")
        return False

    def require(self, plugin_name: str, capability):
        """
        Como check() pero lanza excepción si no tiene permiso.

        Raises:
            PermissionError: si el plugin no tiene la capability.
        """
        if not self.check(plugin_name, capability):
            raise PermissionError(
                f"Plugin '{plugin_name}' no tiene capability "
                f"'{capability.value}'"
            )

    def get_capabilities(self, plugin_name: str) -> Set:
        """Retorna las capabilities de un plugin."""
        with self._lock:
            return set(self._capabilities.get(plugin_name, set()))

    def has_capability(self, plugin_name: str, capability) -> bool:
        """Alias de check()."""
        return self.check(plugin_name, capability)

    def set_strict_mode(self, strict: bool):
        """Activa/desactiva modo estricto (para tests)."""
        self._strict_mode = strict
        logger.info(f"🔒 CapabilityChecker modo estricto: {strict}")

    def _log_denial(self, plugin_name: str, capability, reason: str):
        """Registra y logea una denegación."""
        from .types import Capability

        denial = {
            "plugin": plugin_name,
            "capability": capability.value if isinstance(capability, Capability) else str(capability),
            "reason": reason,
        }

        # Limitar historial
        if len(self._denials) > 1000:
            self._denials = self._denials[-500:]
        self._denials.append(denial)

        logger.warning(
            f"🚫 [capability] Plugin '{plugin_name}' "
            f"DENEGADO '{denial['capability']}': {reason}"
        )

    def get_denials(self) -> List[Dict]:
        """Retorna el historial de denegaciones."""
        with self._lock:
            return list(self._denials)

    def clear(self):
        """Limpia el registro."""
        with self._lock:
            self._capabilities.clear()
            self._denials.clear()


# ==================== SINGLETON ====================

_checker: Optional[CapabilityChecker] = None
_lock = threading.Lock()


def get_capability_checker() -> CapabilityChecker:
    """Obtiene el singleton global."""
    global _checker
    with _lock:
        if _checker is None:
            _checker = CapabilityChecker()
    return _checker


def set_capability_checker(checker: CapabilityChecker):
    """Reemplaza el singleton (para tests)."""
    global _checker
    with _lock:
        _checker = checker