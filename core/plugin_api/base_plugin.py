"""
Clase base para todos los plugins de ProCamera.
"""
from typing import Optional, List, Callable
from abc import ABC, abstractmethod

from utils.logger import get_logger
from .interfaces import PluginContext


class BasePlugin(ABC):
    """
    Clase base para todos los plugins.

    Ciclo de vida:
        __init__     → instanciación (NO usar recursos todavía)
        on_load()    → hooks + UI + recursos
        on_enable()  → activación (registrar processors, activar features)
        on_disable() → desactivación (sin liberar recursos)
        on_unload()  → liberar TODOS los recursos

    Ejemplo mínimo:
        class MyPlugin(BasePlugin):
            NAME = "my_plugin"
            VERSION = "1.0.0"
            DESCRIPTION = "Descripción"

            def on_load(self) -> bool:
                self.logger.info("Cargado")
                return True

            def on_enable(self) -> bool:
                self.logger.info("Activado")
                return True

            def on_disable(self):
                self.logger.info("Desactivado")

            def on_unload(self):
                self.logger.info("Descargado")
    """

    # ==================== METADATOS (SOBRESCRIBIR) ====================

    NAME: str = "unnamed_plugin"
    VERSION: str = "0.0.0"
    DESCRIPTION: str = ""
    AUTHOR: str = ""
    DEPENDENCIES: List[str] = []
    REQUIRES_DEBUG: bool = False

    def __init__(self, context: PluginContext):
        self.context = context
        self.logger = get_logger(f"Plugin.{self.NAME}")

        self._enabled = False
        self._loaded = False
        self._extensions = []
        self._hooks: List[tuple] = []      # (hook_name, callback)

    # En la clase BasePlugin, añade estos métodos:

    # ==================== EXTENSIONES ====================

    def register_extension(self, interface, implementation,
                          priority: int = 50, metadata: dict = None):
        """
        Registra una extensión.
        Se desregistra automáticamente al unload.
        """
        if self.context.extensions is None:
            self.logger.warning("⚠️ No hay ExtensionRegistry")
            return

        self.context.extensions.register(
            interface=interface,
            implementation=implementation,
            priority=priority,
            owner=self.NAME,
            metadata=metadata or {},
        )
        self._extensions.append((interface, implementation))

    def get_extensions(self, interface) -> list:
        """Consulta extensiones registradas de una interfaz."""
        if self.context.extensions is None:
            return []
        return self.context.extensions.get(interface)

    def intercept(self, interface, callback, priority: int = 50):
        """Registra un interceptor para una interfaz."""
        if self.context.extensions is None:
            return
        self.context.extensions.intercept(
            interface, callback, priority=priority, owner=self.NAME
        )

    # Y en __init__, añade:
    # self._extensions = []

    # Y en _do_unload, añade:
    # for interface, impl in self._extensions:
    #     if self.context.extensions:
    #         self.context.extensions.unregister(interface, impl)
    # self._extensions.clear()

    # ==================== CICLO DE VIDA (SOBRESCRIBIR) ====================

    def on_load(self) -> bool:
        """
        Llamado al cargar el plugin.
        Aquí se registran hooks, se crean recursos, se prepara todo.

        Returns:
            True si la carga fue exitosa, False para cancelar.
        """
        return True

    def on_enable(self) -> bool:
        """
        Llamado al activar el plugin.
        Aquí se registran frame processors, se activan features.

        Returns:
            True si la activación fue exitosa, False para cancelar.
        """
        return True

    def on_disable(self):
        """
        Llamado al desactivar el plugin.
        NO liberar recursos aquí — solo pausar la funcionalidad.
        """
        pass

    def on_unload(self):
        """
        Llamado al descargar el plugin.
        Liberar TODOS los recursos: timers, hooks, UI, archivos.
        """
        pass

    def on_settings_changed(self, changed_keys: List[str]):
        """
        Llamado cuando cambia la configuración global.
        Solo se llaman las keys que cambiaron.
        """
        pass

    def get_config_tab(self):
        """
        Retorna un QWidget con la config del plugin.
        Retornar None si el plugin no tiene config UI.
        """
        return None

    # ==================== HELPERS ====================

    def is_enabled(self) -> bool:
        return self._enabled

    def is_loaded(self) -> bool:
        return self._loaded

    def register_hook(self, hook_name: str, callback: Callable, priority: int = 50):
        """
        Registra un callback para un hook.
        Se desregistra automáticamente al unload.
        """
        if self.context.hooks is None:
            self.logger.warning(f"⚠️ No hay hook registry, ignorando registro")
            return

        self.context.hooks.register(
            hook_name=hook_name,
            callback=callback,
            priority=priority,
            owner=self.NAME,
        )
        self._hooks.append((hook_name, callback))

    def emit_hook(self, hook_name: str, **kwargs):
        """Emite un hook para que otros plugins reaccionen."""
        if self.context.hooks is None:
            return []
        return self.context.hooks.emit(hook_name, **kwargs)

    # ==================== MÉTODOS INTERNOS ====================

    def _do_load(self) -> bool:
        """Llamado por el PluginManager."""
        if self._loaded:
            return True

        try:
            self.logger.debug(f"🔌 Cargando plugin '{self.NAME}'...")
            success = self.on_load()

            if success:
                self._loaded = True
                self.logger.info(f"✅ Plugin '{self.NAME}' cargado")
            else:
                self.logger.warning(f"⚠️ Plugin '{self.NAME}' rechazó la carga")

            return success
        except Exception as e:
            self.logger.error(
                f"❌ Error cargando '{self.NAME}': {e}",
                exc_info=True,
            )
            return False

    def _do_enable(self) -> bool:
        """Llamado por el PluginManager."""
        if self._enabled:
            return True

        if not self._loaded:
            if not self._do_load():
                return False

        try:
            self.logger.debug(f"🔌 Activando plugin '{self.NAME}'...")
            success = self.on_enable()

            if success:
                self._enabled = True
                self.logger.info(f"✅ Plugin '{self.NAME}' activado")
            else:
                self.logger.warning(f"⚠️ Plugin '{self.NAME}' rechazó la activación")

            return success
        except Exception as e:
            self.logger.error(
                f"❌ Error activando '{self.NAME}': {e}",
                exc_info=True,
            )
            return False

    def _do_disable(self):
        """Llamado por el PluginManager."""
        if not self._enabled:
            return

        try:
            self.logger.debug(f"🔌 Desactivando plugin '{self.NAME}'...")
            self.on_disable()
            self._enabled = False
            self.logger.info(f"⏸️ Plugin '{self.NAME}' desactivado")
        except Exception as e:
            self.logger.error(
                f"❌ Error desactivando '{self.NAME}': {e}",
                exc_info=True,
            )

    def _do_unload(self):
        """Llamado por el PluginManager."""
        if not self._loaded:
            return

        # Primero desactivar si está activo
        if self._enabled:
            self._do_disable()

        for interface, impl in self._extensions:
            if self.context.extensions:
                self.context.extensions.unregister(interface, impl)
        self._extensions.clear()

        try:
            self.logger.debug(f"🔌 Descargando plugin '{self.NAME}'...")

            # Desregistrar hooks automáticamente
            if self.context.hooks is not None:
                self.context.hooks.unregister_all_from(self.NAME)
            self._hooks.clear()

            # Llamar al unload del plugin
            self.on_unload()

            self._loaded = False
            self.logger.info(f"🔌 Plugin '{self.NAME}' descargado")
        except Exception as e:
            self.logger.error(
                f"❌ Error descargando '{self.NAME}': {e}",
                exc_info=True,
            )

    # ==================== CAPABILITIES ====================

    def has_capability(self, capability) -> bool:
        """
        Verifica si el plugin tiene una capability.

        Uso:
            if self.has_capability(Capability.NETWORK):
                # hacer peticiones HTTP
        """
        try:
            from core.extensions.capability_checker import get_capability_checker
            checker = get_capability_checker()
            return checker.check(self.NAME, capability)
        except Exception:
            return False

    def require_capability(self, capability):
        """
        Como has_capability() pero lanza excepción si no tiene permiso.

        Uso:
            self.require_capability(Capability.WRITE_FILES)
        """
        from core.extensions.capability_checker import get_capability_checker
        checker = get_capability_checker()
        checker.require(self.NAME, capability)

    def get_capabilities(self) -> list:
        """Retorna las capabilities declaradas por este plugin."""
        try:
            from core.extensions.capability_checker import get_capability_checker
            checker = get_capability_checker()
            return list(checker.get_capabilities(self.NAME))
        except Exception:
            return []

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} name='{self.NAME}' "
            f"v{self.VERSION} loaded={self._loaded} enabled={self._enabled}>"
        )