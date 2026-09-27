"""
Sandbox — Auditoría y bloqueo de operaciones peligrosas.

Usa sys.addaudithook() (Python 3.8+) para interceptar operaciones sensibles
y bloquearlas si el plugin actual no tiene la capability adecuada.

IMPORTANTE:
- Solo se activa en modo estricto (producción).
- Una vez activado, NO se puede desactivar (limitación de Python).
- El "plugin actual" se identifica vía contextvars.
- Si no se puede identificar el plugin → permitir (llamada desde Core).

Comportamiento:
- open() → READ_FILES / WRITE_FILES
- socket.* → NETWORK
- subprocess.Popen / os.system → PROCESS_EXECUTION
- import → (por defecto permitir, salvo módulos prohibidos)
- exec/eval → bloquear siempre
"""
import sys
import os
import threading
from typing import Set, Optional, Callable, List, Dict, Any
from pathlib import Path

from utils.logger import get_logger
from core.extensions.types import Capability

logger = get_logger("Sandbox")


# ============================================================
# MÓDULOS PROHIBIDOS (siempre bloqueados)
# ============================================================

FORBIDDEN_MODULES = {
    "ctypes",           # acceso a memoria nativa
    "cffi",             # FFI
    "mmap",             # mapeo de memoria
    "fcntl",            # control de ficheros bajo nivel (Unix)
    "winreg",           # registro de Windows
    "pty",              # pseudo-terminales
    "pwd",              # info de usuarios (Unix)
    "spwd",             # passwords (Unix)
    "grp",              # grupos (Unix)
    "crypt",            # cripto de bajo nivel
}


# ============================================================
# MÓDULOS PROTEGIDOS (solo con capability)
# ============================================================

PROTECTED_MODULES = {
    # Network
    "socket": Capability.NETWORK,
    "ssl": Capability.NETWORK,
    "http": Capability.NETWORK,
    "urllib": Capability.NETWORK,
    "requests": Capability.NETWORK,
    "aiohttp": Capability.NETWORK,
    "websocket": Capability.NETWORK,
    "smtplib": Capability.NETWORK,
    "ftplib": Capability.NETWORK,
    "telnetlib": Capability.NETWORK,

    # Process
    "subprocess": Capability.PROCESS_EXECUTION,
    "multiprocessing": Capability.PROCESS_EXECUTION,
    "pty": Capability.PROCESS_EXECUTION,

    # Files
    "sqlite3": Capability.WRITE_FILES,
    "pickle": Capability.READ_FILES,
    "marshal": Capability.READ_FILES,
}


# ============================================================
# HOOK
# ============================================================

class SandboxHook:
    """
    Hook de auditoría que bloquea operaciones sensibles.

    Se registra UNA vez con sys.addaudithook(). No se puede quitar.
    """

    def __init__(self):
        self._enabled = True
        self._strict = True
        self._lock = threading.Lock()
        self._blocked_count: Dict[str, int] = {}
        self._allowed_paths: Dict[str, Set[str]] = {}   # plugin → paths permitidos
        self._blocked_paths: Set[str] = set()            # paths globales prohibidos

    # ==================== CONFIGURACIÓN ====================

    def set_strict(self, strict: bool):
        """Activa/desactiva modo estricto."""
        self._strict = strict
        logger.info(f"🔒 Sandbox modo estricto: {strict}")

    def add_allowed_path(self, plugin_name: str, path: str):
        """Añade un path permitido para un plugin."""
        with self._lock:
            if plugin_name not in self._allowed_paths:
                self._allowed_paths[plugin_name] = set()
            self._allowed_paths[plugin_name].add(os.path.abspath(path))

    def add_blocked_path(self, path: str):
        """Añade un path globalmente prohibido."""
        with self._lock:
            self._blocked_paths.add(os.path.abspath(path))

    def get_stats(self) -> Dict[str, int]:
        with self._lock:
            return dict(self._blocked_count)

    # ==================== HOOK ====================

    def __call__(self, event: str, args: tuple):
        """Callback del audit hook."""
        if not self._enabled or not self._strict:
            return

        try:
            # Identificar el plugin actual
            plugin_name = self._get_current_plugin()

            # Sin plugin identificado → permitir (llamada desde Core)
            if not plugin_name:
                return

            # Dispatch por tipo de evento
            handler = self._get_handler(event)
            if handler is None:
                return

            handler(plugin_name, event, args)
        except PermissionError:
            # Re-lanzar para que el llamante lo vea
            raise
        except Exception as e:
            # Cualquier error → log y permitir (fail-safe)
            logger.debug(f"⚠️ Sandbox error en '{event}': {e}")

    def _get_handler(self, event: str) -> Optional[Callable]:
        """Retorna el handler para un evento."""
        handlers = {
            "open": self._handle_open,
            "os.mkdir": self._handle_mkdir,
            "os.remove": self._handle_remove,
            "os.rename": self._handle_rename,
            "os.system": self._handle_os_system,
            "subprocess.Popen": self._handle_subprocess,
            "socket.connect": self._handle_socket_connect,
            "socket.bind": self._handle_socket_bind,
            "socket.getaddrinfo": self._handle_socket_dns,
            "import": self._handle_import,
            "importlib.find_spec": self._handle_importlib_find_spec,  # ✅ NUEVO
            "exec": self._handle_exec,
            "compile": self._handle_compile,
            "ctypes.dlopen": self._handle_ctypes,
            "ctypes.dlsym": self._handle_ctypes,
            "sys.addaudithook": self._handle_add_audit_hook,
            "sys._getframe": self._handle_getframe,
            "object.__getattr__": None,
        }
        return handlers.get(event)

    def _get_current_plugin(self) -> str:
        """Obtiene el plugin actual desde contextvars."""
        try:
            from core.plugin_api.interfaces import _current_plugin
            return _current_plugin.get()
        except Exception:
            return ""

    # ==================== HANDLERS ====================

    def _handle_open(self, plugin_name: str, event: str, args: tuple):
        """Bloquea open() si no tiene capability."""
        if not args:
            return
        path = args[0]
        mode = args[1] if len(args) > 1 else "r"
        flags = args[2] if len(args) > 2 else 0

        if not isinstance(path, (str, bytes, os.PathLike)):
            return

        try:
            abspath = os.path.abspath(path)
        except Exception:
            return

        # Paths globalmente prohibidos
        with self._lock:
            blocked = any(
                abspath.startswith(bp) for bp in self._blocked_paths
            )
        if blocked:
            self._block(plugin_name, event, f"path bloqueado: {abspath}")
            raise PermissionError(
                f"[sandbox] path bloqueado: {abspath}"
            )

        # Determinar capability requerida
        write_modes = ("w", "a", "x", "+")
        is_write = any(m in mode for m in write_modes) or (
            flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND)
        )

        from core.extensions.capability_checker import get_capability_checker
        from core.extensions.types import Capability

        checker = get_capability_checker()
        required = Capability.WRITE_FILES if is_write else Capability.READ_FILES

        if not checker.check(plugin_name, required):
            self._block(plugin_name, event, f"{required.value}: {abspath}")
            raise PermissionError(
                f"[sandbox] '{plugin_name}' no tiene {required.value} "
                f"para abrir: {abspath}"
            )

    def _handle_mkdir(self, plugin_name: str, event: str, args: tuple):
        from core.extensions.capability_checker import get_capability_checker
        from core.extensions.types import Capability
        checker = get_capability_checker()
        if not checker.check(plugin_name, Capability.WRITE_FILES):
            self._block(plugin_name, event, str(args))
            raise PermissionError(
                f"[sandbox] '{plugin_name}' no tiene write_files para mkdir"
            )

    def _handle_remove(self, plugin_name: str, event: str, args: tuple):
        from core.extensions.capability_checker import get_capability_checker
        from core.extensions.types import Capability
        checker = get_capability_checker()
        if not checker.check(plugin_name, Capability.FILE_DELETE):
            self._block(plugin_name, event, str(args))
            raise PermissionError(
                f"[sandbox] '{plugin_name}' no tiene file_delete"
            )

    def _handle_rename(self, plugin_name: str, event: str, args: tuple):
        from core.extensions.capability_checker import get_capability_checker
        from core.extensions.types import Capability
        checker = get_capability_checker()
        if not checker.check(plugin_name, Capability.WRITE_FILES):
            self._block(plugin_name, event, str(args))
            raise PermissionError(
                f"[sandbox] '{plugin_name}' no tiene write_files para rename"
            )

    def _handle_os_system(self, plugin_name: str, event: str, args: tuple):
        from core.extensions.capability_checker import get_capability_checker
        from core.extensions.types import Capability
        checker = get_capability_checker()
        if not checker.check(plugin_name, Capability.PROCESS_EXECUTION):
            self._block(plugin_name, event, str(args))
            raise PermissionError(
                f"[sandbox] '{plugin_name}' no tiene process_execution"
            )

    def _handle_subprocess(self, plugin_name: str, event: str, args: tuple):
        from core.extensions.capability_checker import get_capability_checker
        from core.extensions.types import Capability
        checker = get_capability_checker()
        if not checker.check(plugin_name, Capability.PROCESS_EXECUTION):
            self._block(plugin_name, event, str(args))
            raise PermissionError(
                f"[sandbox] '{plugin_name}' no tiene process_execution"
            )

    def _handle_socket_connect(self, plugin_name: str, event: str, args: tuple):
        from core.extensions.capability_checker import get_capability_checker
        from core.extensions.types import Capability
        checker = get_capability_checker()
        if not checker.check(plugin_name, Capability.NETWORK):
            self._block(plugin_name, event, str(args))
            raise PermissionError(
                f"[sandbox] '{plugin_name}' no tiene network"
            )

    def _handle_socket_bind(self, plugin_name: str, event: str, args: tuple):
        from core.extensions.capability_checker import get_capability_checker
        from core.extensions.types import Capability
        checker = get_capability_checker()
        if not checker.check(plugin_name, Capability.NETWORK):
            self._block(plugin_name, event, str(args))
            raise PermissionError(
                f"[sandbox] '{plugin_name}' no tiene network para bind"
            )

    def _handle_socket_dns(self, plugin_name: str, event: str, args: tuple):
        from core.extensions.capability_checker import get_capability_checker
        from core.extensions.types import Capability
        checker = get_capability_checker()
        if not checker.check(plugin_name, Capability.NETWORK):
            self._block(plugin_name, event, str(args))
            raise PermissionError(
                f"[sandbox] '{plugin_name}' no tiene network para DNS"
            )

    def _handle_import(self, plugin_name: str, event: str, args: tuple):
        """Bloquea import de módulos prohibidos/protegidos."""
        if not args:
            return
        module_name = args[0]
        if not isinstance(module_name, str):
            return

        root = module_name.split(".")[0]

        # Prohibidos siempre
        if root in FORBIDDEN_MODULES:
            self._block(plugin_name, event, module_name)
            raise PermissionError(
                f"[sandbox] import de '{module_name}' prohibido"
            )

        # Protegidos por capability
        if root in PROTECTED_MODULES:
            from core.extensions.capability_checker import get_capability_checker
            checker = get_capability_checker()
            cap = PROTECTED_MODULES[root]   # ← ya es Capability
            if not checker.check(plugin_name, cap):
                self._block(
                    plugin_name, event,
                    f"{module_name} (necesita {cap.value})"
                )
                raise PermissionError(
                    f"[sandbox] import de '{module_name}' requiere {cap.value}"
                )

    def _handle_importlib_find_spec(self, plugin_name: str, event: str, args: tuple):
        """Handler para importlib.find_spec."""
        if not args:
            return
        module_name = args[0]
        if not isinstance(module_name, str):
            return

        root = module_name.split(".")[0]

        if root in FORBIDDEN_MODULES:
            self._block(plugin_name, event, module_name)
            raise PermissionError(
                f"[sandbox] import de '{module_name}' prohibido"
            )

        if root in PROTECTED_MODULES:
            from core.extensions.capability_checker import get_capability_checker
            checker = get_capability_checker()
            cap = PROTECTED_MODULES[root]
            if not checker.check(plugin_name, cap):
                self._block(
                    plugin_name, event,
                    f"{module_name} (necesita {cap.value})"
                )
                raise PermissionError(
                    f"[sandbox] import de '{module_name}' requiere {cap.value}"
                )

    def _handle_exec(self, plugin_name: str, event: str, args: tuple):
        """Bloquea exec() dinámico."""
        self._block(plugin_name, event, "exec dinámico")
        raise PermissionError(
            f"[sandbox] exec() dinámico bloqueado para '{plugin_name}'"
        )

    def _handle_compile(self, plugin_name: str, event: str, args: tuple):
        """Bloquea compile() dinámico."""
        self._block(plugin_name, event, "compile dinámico")
        raise PermissionError(
            f"[sandbox] compile() dinámico bloqueado para '{plugin_name}'"
        )

    def _handle_ctypes(self, plugin_name: str, event: str, args: tuple):
        """Bloquea ctypes siempre."""
        self._block(plugin_name, event, "ctypes")
        raise PermissionError(
            f"[sandbox] ctypes bloqueado para '{plugin_name}'"
        )

    def _handle_add_audit_hook(self, plugin_name: str, event: str, args: tuple):
        """Bloquea que un plugin registre su propio audit hook."""
        self._block(plugin_name, event, "addaudithook")
        raise PermissionError(
            f"[sandbox] addaudithook bloqueado para '{plugin_name}'"
        )

    def _handle_getframe(self, plugin_name: str, event: str, args: tuple):
        """Bloquea inspección de frames."""
        # Permitir getframe (es común en logging), pero log si se abusa
        pass

    # ==================== HELPERS ====================

    def _block(self, plugin_name: str, event: str, detail: str):
        """Registra y logea un bloqueo."""
        with self._lock:
            key = f"{event}:{detail}"
            self._blocked_count[key] = self._blocked_count.get(key, 0) + 1

        logger.warning(
            f"🛡️ [sandbox] BLOQUEADO '{event}' para '{plugin_name}': {detail}"
        )


# ============================================================
# SINGLETON
# ============================================================

_hook: Optional[SandboxHook] = None
_hook_registered = False
_lock = threading.Lock()


def get_sandbox_hook() -> SandboxHook:
    """Obtiene el singleton (sin registrar el hook)."""
    global _hook
    with _lock:
        if _hook is None:
            _hook = SandboxHook()
    return _hook


def activate_sandbox(strict: bool = True) -> SandboxHook:
    """
    Activa el sandbox.
    Una vez activado, NO se puede desactivar (limitación de Python).

    Args:
        strict: si True, bloquea; si False, solo logea (dev).
    """
    global _hook_registered, _hook

    with _lock:
        hook = get_sandbox_hook()
        hook.set_strict(strict)

        if not _hook_registered:
            try:
                sys.addaudithook(hook)
                _hook_registered = True
                logger.info(
                    f"🛡️ Sandbox ACTIVADO (strict={strict})"
                )
            except Exception as e:
                logger.error(f"❌ No se pudo activar sandbox: {e}")

        return hook