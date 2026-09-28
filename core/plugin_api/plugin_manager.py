"""
Gestor central de plugins.

Responsabilidades:
- Descubrir plugins en el directorio `plugins/`
- Cargar/descargar plugins
- Activar/desactivar plugins
- Orquestar el ciclo de vida
- Aislar fallos (un plugin que falla no rompe otros)
"""
import os
import sys
import json
import threading
import importlib.util
from typing import Dict, List, Optional, Set, Tuple

from utils.logger import get_logger
from plugins.package_validator import ValidationResult
from .interfaces import PluginContext, PluginMetadata
from .base_plugin import BasePlugin
from .hooks import get_hook_registry

logger = get_logger("PluginManager")


# ==================== ERRORES ====================

class PluginError(Exception):
    """Error base de plugins."""
    pass


class PluginNotFoundError(PluginError):
    """El plugin no existe."""
    pass


class PluginDependencyError(PluginError):
    """Falta una dependencia."""
    pass


class PluginLoadError(PluginError):
    """Error cargando el plugin."""
    pass


# ==================== MANAGER ====================

class PluginManager:
    """
    Gestor de plugins.

    Uso:
        pm = PluginManager()
        pm.discover("plugins/")
        pm.load_all()
        pm.enable("motion_detector")
    """

    def __init__(self):
        self._plugins: Dict[str, BasePlugin] = {}
        self._metadata: Dict[str, PluginMetadata] = {}
        self._enabled: Set[str] = set()
        self._loaded: Set[str] = set()
        self._failed: Set[str] = set()

        # Contexto global (compartido entre plugins)
        self.context = PluginContext()
        self.context.hooks = get_hook_registry()

        # Path de plugins
        self._plugins_dir: Optional[str] = None

        # Estadísticas
        self._stats = {
            "total_discovered": 0,
            "total_loaded": 0,
            "total_enabled": 0,
            "total_failed": 0,
        }

        logger.info("🎛️ PluginManager inicializado")

    # ==================== DESCUBRIMIENTO ====================

    def discover(self, plugins_dir: str) -> int:
        """
        Escanea el directorio de plugins y registra metadatos.

        Soporta:
        - Carpetas: plugins/<name>/
        - Paquetes ZIP: plugins/<name>.zip

        Auto-registro de manifests:
        - Cada plugin puede tener su propio manifest.json en su carpeta.
        - El manifest global (plugins/manifest.json) es opcional y sirve
          como override.
        - Los campos del manifest local tienen prioridad.
        """
        from core.plugin_api.manifest_loader import get_manifest_loader

        self._plugins_dir = plugins_dir

        if not os.path.isdir(plugins_dir):
            logger.error(f"❌ Directorio de plugins no existe: {plugins_dir}")
            return 0

        # Cargar manifest global si existe
        manifest_loader = get_manifest_loader()
        global_manifest_path = os.path.join(plugins_dir, "manifest.json")
        manifest_loader.load_global(global_manifest_path)

        # Extraer paquetes ZIP primero
        zip_plugins = self._install_zip_packages(plugins_dir)

        discovered = 0
        searched_paths: List[Tuple[str, str]] = []  # (name, path)

        # 1. Subdirectorios directos
        for entry in os.listdir(plugins_dir):
            plugin_path = os.path.join(plugins_dir, entry)
            if os.path.isdir(plugin_path):
                if not self._is_valid_plugin_dir(plugin_path):
                    continue
                if entry.startswith("_") or entry.startswith("."):
                    continue
                searched_paths.append((entry, plugin_path))

        # 2. Paquetes extraídos
        for pkg_name, pkg_path in zip_plugins:
            searched_paths.append((pkg_name, pkg_path))

        # 3. Registrar cada plugin con su manifest resuelto
        for entry, plugin_path in searched_paths:
            if entry in self._metadata:
                logger.debug(f"⚠️ Plugin '{entry}' ya registrado, saltando")
                continue

            # Resolver manifest (local + global + defaults)
            resolved = manifest_loader.resolve(entry, plugin_path)

            metadata = PluginMetadata(
                name=entry,
                version=resolved.version,
                description=resolved.description,
                author=resolved.author,
                dependencies=list(resolved.dependencies),
                requires_debug=resolved.requires_debug,
                enabled_by_default=resolved.enabled_by_default,
                auto_load=resolved.auto_load,
                path=os.path.abspath(plugin_path),
                module_name=entry,
                capabilities=list(resolved.capabilities),
            )

            self._metadata[entry] = metadata
            discovered += 1
            logger.debug(
                f"🔍 Descubierto: {entry} (v{metadata.version}, "
                f"src={resolved.source}) en {plugin_path}"
            )

        self._stats["total_discovered"] = discovered
        logger.info(f"🔍 {discovered} plugin(s) descubierto(s)")

        return discovered

    # ==================== ZIP PACKAGES ====================

    def _is_valid_plugin_dir(self, path: str) -> bool:
        """Verifica si un directorio es un plugin válido."""
        has_init = os.path.isfile(os.path.join(path, "__init__.py"))
        has_plugin = os.path.isfile(os.path.join(path, "plugin.py"))
        return has_init or has_plugin

    def _install_zip_packages(self, plugins_dir: str) -> List[Tuple[str, str]]:
        """
        Extrae todos los paquetes .zip encontrados.

        Returns:
            Lista de (plugin_name, install_path).
        """
        try:
            from plugins.package_loader import get_package_loader
        except ImportError as e:
            logger.debug(f"⚠️ PackageLoader no disponible: {e}")
            return []

        try:
            loader = get_package_loader(plugins_dir)
        except Exception as e:
            logger.error(f"❌ Error creando PackageLoader: {e}")
            return []

        # Escanear
        try:
            packages = loader.scan()
        except Exception as e:
            logger.error(f"❌ Error escaneando paquetes: {e}", exc_info=True)
            return []

        if not packages:
            return []

        logger.info(f"📦 Procesando {len(packages)} paquete(s) .zip")

        # Extraer
        extracted_count = loader.install_all(packages)
        logger.info(
            f"📦 {extracted_count}/{len(packages)} paquete(s) extraído(s)"
        )

        # Retornar rutas
        result = []
        valid_paths = set()
        for pkg in packages:
            if os.path.isdir(pkg.install_path):
                # Verificar que sea un plugin válido
                if self._is_valid_plugin_dir(pkg.install_path):
                    # El nombre del plugin es el nombre del ZIP sin versión
                    plugin_name = pkg.name
                    # Evitar colisiones con directorios nativos
                    if os.path.isdir(os.path.join(plugins_dir, plugin_name)):
                        plugin_name = f"{pkg.name}_zip"
                        logger.debug(
                            f"⚠️ Colisión '{pkg.name}' con directorio nativo, "
                            f"usando '{plugin_name}'"
                        )
                    result.append((plugin_name, pkg.install_path))
                    valid_paths.add(pkg.install_path)
                else:
                    logger.warning(
                        f"⚠️ Paquete '{pkg.name}' extraído pero no es "
                        f"plugin válido"
                    )

        # Cleanup de huérfanos
        try:
            loader.cleanup_orphans(valid_paths)
        except Exception as e:
            logger.debug(f"⚠️ Error en cleanup: {e}")

        return result

    def validate_package(self, zip_path: str) -> 'ValidationResult':
        """
        Valida un paquete .zip sin instalarlo.

        Returns:
            ValidationResult con valid=True/False + errores + warnings.
        """
        try:
            from plugins.package_validator import get_package_validator
            validator = get_package_validator()
            return validator.validate_zip(zip_path)
        except Exception as e:
            result = ValidationResult()
            result.add_error(f"Error validando: {e}")
            return result

    # ==================== IMPORTACIÓN ====================

    def _import_plugin_module(self, metadata: PluginMetadata):
        """
        Importa el módulo `plugin.py` de un plugin usando su path absoluto.

        Esto evita problemas con sys.path y permite que los plugins
        estén en cualquier ubicación.
        """
        plugin_file = os.path.join(metadata.path, "plugin.py")

        if not os.path.isfile(plugin_file):
            logger.error(f"❌ No existe plugin.py en {metadata.path}")
            return None

        # ✅ Nombre único para evitar colisiones en sys.modules
        module_name = f"procamara_plugin_{metadata.name}"

        # ✅ Eliminar si ya estaba cargado (para reimportar limpio)
        if module_name in sys.modules:
            del sys.modules[module_name]

        try:
            spec = importlib.util.spec_from_file_location(
                module_name,
                plugin_file,
                submodule_search_locations=[metadata.path],
            )
            if spec is None or spec.loader is None:
                logger.error(
                    f"❌ No se pudo crear spec para '{metadata.name}'"
                )
                return None

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            logger.debug(
                f"✅ [import] '{module_name}' desde {plugin_file}"
            )
            return module

        except Exception as e:
            logger.error(
                f"❌ Error importando '{metadata.name}': "
                f"{type(e).__name__}: {e}",
                exc_info=True,
            )
            sys.modules.pop(module_name, None)
            return None

    # ==================== CARGA ====================

    def load(self, plugin_name: str) -> bool:
        """
        Carga un plugin.

        Returns:
            True si cargó correctamente.
        """
        if plugin_name in self._loaded:
            logger.debug(f"🔌 Plugin '{plugin_name}' ya cargado")
            return True

        if plugin_name in self._failed:
            logger.warning(f"⚠️ Plugin '{plugin_name}' falló anteriormente")
            return False

        metadata = self._metadata.get(plugin_name)
        if metadata is None:
            logger.error(f"❌ Plugin '{plugin_name}' no descubierto")
            raise PluginNotFoundError(plugin_name)

        # Verificar dependencias
        for dep in metadata.dependencies:
            if dep not in self._loaded:
                logger.debug(
                    f"🔌 Cargando dependencia '{dep}' de '{plugin_name}'..."
                )
                if not self.load(dep):
                    raise PluginDependencyError(
                        f"'{plugin_name}' requiere '{dep}'"
                    )

        # Verificar debug
        if metadata.requires_debug and not self.context.is_debug:
            logger.debug(
                f"⏸️ Plugin '{plugin_name}' requiere debug, saltando"
            )
            return False

        # ✅ Importar el módulo (con path absoluto)
        plugin_module = self._import_plugin_module(metadata)
        if plugin_module is None:
            self._failed.add(plugin_name)
            self._stats["total_failed"] += 1
            return False

        # Buscar la clase del plugin
        plugin_class = self._find_plugin_class(plugin_module, plugin_name)
        if plugin_class is None:
            logger.error(
                f"❌ No se encontró clase de plugin en '{plugin_name}'"
            )
            self._failed.add(plugin_name)
            self._stats["total_failed"] += 1
            return False

        # Instanciar
        try:
            # Registrar capabilities en el checker
            from core.extensions.capability_checker import get_capability_checker
            checker = get_capability_checker()
            checker.register_plugin(plugin_name, metadata.capabilities)

            # ✅ NUEVO: Sandbox — añadir paths permitidos del plugin
            try:
                from core.extensions.sandbox import get_sandbox_hook
                hook = get_sandbox_hook()
                # El plugin puede leer/escribir en su propio directorio
                hook.add_allowed_path(plugin_name, metadata.path)
            except Exception:
                pass

            # Actualizar contexto
            self.context.plugin_dir = metadata.path
            self.context.plugin_name = plugin_name

            instance = plugin_class(self.context)
            instance._do_load()

            if instance.is_loaded():
                self._plugins[plugin_name] = instance
                self._loaded.add(plugin_name)
                self._stats["total_loaded"] += 1
                logger.info(f"✅ Plugin cargado: {plugin_name}")
                return True
            else:
                self._failed.add(plugin_name)
                self._stats["total_failed"] += 1
                return False

        except Exception as e:
            logger.error(
                f"❌ Error instanciando '{plugin_name}': {e}",
                exc_info=True,
            )
            self._failed.add(plugin_name)
            self._stats["total_failed"] += 1
            return False

    def check_capability(self, plugin_name: str, capability) -> bool:
        """Verifica si un plugin tiene una capability (para uso externo)."""
        from core.extensions.capability_checker import get_capability_checker
        return get_capability_checker().check(plugin_name, capability)

    def _find_plugin_class(self, module, plugin_name: str):
        """Busca una subclase de BasePlugin en el módulo."""
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (isinstance(attr, type) and
                    issubclass(attr, BasePlugin) and
                    attr is not BasePlugin):
                return attr
        return None

    # ==================== DESCARGA ====================

    def unload(self, plugin_name: str) -> bool:
        plugin = self._plugins.get(plugin_name)
        if plugin is None:
            return False

        try:
            plugin._do_unload()
        except Exception as e:
            logger.error(
                f"❌ Error descargando '{plugin_name}': {e}",
                exc_info=True,
            )

        self._plugins.pop(plugin_name, None)
        self._loaded.discard(plugin_name)
        self._enabled.discard(plugin_name)

        # ✅ NUEVO: resetear capabilities
        try:
            from core.extensions.capability_checker import get_capability_checker
            checker = get_capability_checker()
            # No desregistramos, solo log
            logger.debug(f"🔒 Capabilities de '{plugin_name}' liberadas")
        except Exception:
            pass

        logger.info(f"🔌 Plugin descargado: {plugin_name}")
        return True

    # ==================== ACTIVACIÓN ====================

    def enable(self, plugin_name: str) -> bool:
        """Activa un plugin."""
        if plugin_name in self._enabled:
            return True

        # Cargar si no está cargado
        if plugin_name not in self._loaded:
            if not self.load(plugin_name):
                return False

        plugin = self._plugins.get(plugin_name)
        if plugin is None:
            return False

        if plugin._do_enable():
            self._enabled.add(plugin_name)
            self._stats["total_enabled"] += 1
            return True

        return False

    def disable(self, plugin_name: str) -> bool:
        """Desactiva un plugin."""
        if plugin_name not in self._enabled:
            return True

        plugin = self._plugins.get(plugin_name)
        if plugin is None:
            return False

        plugin._do_disable()
        self._enabled.discard(plugin_name)
        return True

    # ==================== OPERACIONES MASIVAS ====================

    def load_all(self, enabled_only: bool = True) -> int:
        """Carga todos los plugins descubiertos."""
        count = 0
        for name in list(self._metadata.keys()):
            metadata = self._metadata[name]

            if enabled_only and not metadata.enabled_by_default:
                continue
            if not metadata.auto_load:
                continue

            try:
                if self.load(name):
                    count += 1
            except Exception as e:
                logger.error(f"❌ Error cargando '{name}': {e}")

        logger.info(f"✅ {count}/{len(self._metadata)} plugin(s) cargado(s)")
        return count

    def enable_all(self) -> int:
        """Activa todos los plugins cargados."""
        count = 0
        for name in list(self._loaded):
            try:
                if self.enable(name):
                    count += 1
            except Exception as e:
                logger.error(f"❌ Error activando '{name}': {e}")

        logger.info(f"✅ {count} plugin(s) activado(s)")
        return count

    def disable_all(self) -> int:
        """Desactiva todos los plugins activos."""
        count = 0
        for name in list(self._enabled):
            try:
                if self.disable(name):
                    count += 1
            except Exception as e:
                logger.error(f"❌ Error desactivando '{name}': {e}")

        logger.info(f"⏸️ {count} plugin(s) desactivado(s)")
        return count

    def unload_all(self):
        """Descarga todos los plugins."""
        self.disable_all()
        for name in list(self._loaded):
            try:
                self.unload(name)
            except Exception as e:
                logger.error(f"❌ Error descargando '{name}': {e}")

        logger.info("🔌 Todos los plugins descargados")

    # ==================== CONSULTAS ====================

    def get(self, plugin_name: str) -> Optional[BasePlugin]:
        """Retorna un plugin por nombre."""
        return self._plugins.get(plugin_name)

    def get_all(self) -> Dict[str, BasePlugin]:
        """Retorna todos los plugins cargados."""
        return dict(self._plugins)

    def get_metadata(self, plugin_name: str) -> Optional[PluginMetadata]:
        """Retorna metadata de un plugin."""
        return self._metadata.get(plugin_name)

    def get_all_metadata(self) -> Dict[str, PluginMetadata]:
        """Retorna metadata de todos los plugins descubiertos."""
        return dict(self._metadata)

    def list_discovered(self) -> List[str]:
        """Lista plugins descubiertos."""
        return list(self._metadata.keys())

    def list_loaded(self) -> List[str]:
        """Lista plugins cargados."""
        return list(self._loaded)

    def list_enabled(self) -> List[str]:
        """Lista plugins activos."""
        return list(self._enabled)

    def list_failed(self) -> List[str]:
        """Lista plugins que fallaron."""
        return list(self._failed)

    def is_loaded(self, plugin_name: str) -> bool:
        return plugin_name in self._loaded

    def is_enabled(self, plugin_name: str) -> bool:
        return plugin_name in self._enabled

    def get_stats(self) -> Dict:
        """Estadísticas del manager."""
        return {
            **self._stats,
            "currently_loaded": len(self._loaded),
            "currently_enabled": len(self._enabled),
            "currently_failed": len(self._failed),
        }

    # ==================== PLUGIN WRAPPERS ====================

    def _get_wrappers_for(self, plugin_name: str) -> list:
        """
        Retorna los wrappers registrados que aplican a este plugin.

        Los wrappers se obtienen del ExtensionRegistry. Si no hay
        registry, retorna lista vacía.
        """
        try:
            from core.extension_registry import get_extension_registry
            from core.extensions.interfaces import PluginWrapper

            registry = get_extension_registry()
            if registry is None:
                return []

            wrappers = []
            for w in registry.get(PluginWrapper):
                try:
                    if w.wraps_plugin(plugin_name):
                        wrappers.append(w)
                except Exception:
                    continue
            return wrappers
        except Exception:
            return []

    def call_plugin_method(
        self, plugin_name: str, method_name: str, *args, **kwargs
    ):
        """
        Invoca un método de un plugin aplicando los PluginWrapper
        registrados.

        Orden de ejecución:
          1. before_call() de cada wrapper
          2. método real del plugin
          3. after_call() de cada wrapper (en orden inverso)
          4. on_error() si el método falla

        Returns:
            Resultado del método (posiblemente modificado por wrappers).

        Raises:
            PluginNotFoundError si el plugin no está cargado.
        """
        plugin = self._plugins.get(plugin_name)
        if plugin is None:
            raise PluginNotFoundError(plugin_name)

        method = getattr(plugin, method_name, None)
        if method is None:
            raise PluginError(
                f"Plugin '{plugin_name}' no tiene método '{method_name}'"
            )

        wrappers = self._get_wrappers_for(plugin_name)

        # === Pre-call ===
        for w in wrappers:
            try:
                w.before_call(plugin_name, method_name, args, kwargs)
            except Exception as e:
                logger.error(
                    f"❌ PluginWrapper.before_call falló: {e}",
                    exc_info=True,
                )

        # === Ejecutar ===
        try:
            result = method(*args, **kwargs)
        except Exception as e:
            # Notificar wrappers del error
            for w in wrappers:
                try:
                    w.on_error(plugin_name, method_name, e)
                except Exception as e2:
                    logger.error(f"❌ PluginWrapper.on_error falló: {e2}")
            raise

        # === Post-call (orden inverso) ===
        for w in reversed(wrappers):
            try:
                new_result = w.after_call(plugin_name, method_name, result)
                if new_result is not None:
                    result = new_result
            except Exception as e:
                logger.error(
                    f"❌ PluginWrapper.after_call falló: {e}",
                    exc_info=True,
                )

        return result

    def get_wrappers_for(self, plugin_name: str) -> list:
        """Retorna los wrappers activos para un plugin (público)."""
        return self._get_wrappers_for(plugin_name)

    # ==================== SET CONTEXT ====================

    def set_context_apis(
        self,
        settings=None,
        cameras=None,
        frames=None,
        ui=None,
        files=None,
        notifications=None,
        timers=None,
        extensions=None,
        services=None,
    ):
        """
        Inyecta las APIs en el contexto.

        Se llama DESPUÉS de crear MainWindow, cuando las APIs están listas.

        Nota: cada plugin crea su propio logger, no hay logger global.
        """
        if settings is not None:
            self.context.settings = settings
        if cameras is not None:
            self.context.cameras = cameras
        if frames is not None:
            self.context.frames = frames
        if ui is not None:
            self.context.ui = ui
        if files is not None:
            self.context.files = files
        if notifications is not None:
            self.context.notifications = notifications
        if timers is not None:
            self.context.timers = timers
        if extensions is not None:
            self.context.extensions = extensions
        if services is not None:
            self.context.services = services

        logger.debug(
            f"✅ APIs inyectadas: "
            f"settings={settings is not None}, "
            f"cameras={cameras is not None}, "
            f"frames={frames is not None}, "
            f"ui={ui is not None}, "
            f"extensions={extensions is not None}, "
            f"services={services is not None}"
        )

    # ==================== GESTIÓN (para GUI) ====================

    def get_plugin_info(self, plugin_name: str) -> Optional[dict]:
        """
        Retorna info completa de un plugin para la GUI.

        Incluye readme_content y readme_path si el plugin tiene README.md.
        """
        metadata = self._metadata.get(plugin_name)
        if metadata is None:
            return None

        plugin = self._plugins.get(plugin_name)
        is_loaded = plugin_name in self._loaded
        is_enabled = plugin_name in self._enabled
        is_failed = plugin_name in self._failed

        # Capabilities
        capabilities = []
        try:
            from core.extensions.capability_checker import get_capability_checker
            checker = get_capability_checker()
            capabilities = sorted(
                c.value for c in checker.get_capabilities(plugin_name)
            )
        except Exception:
            pass

        # Extensiones registradas
        extensions = []
        try:
            from core.extension_registry import get_extension_registry
            registry = get_extension_registry()
            for interface in registry.list_interfaces():
                entries = registry._extensions.get(interface, [])
                for entry in entries:
                    if entry.owner == plugin_name:
                        extensions.append({
                            "interface": interface.__name__,
                            "priority": entry.priority,
                        })
        except Exception:
            pass

        # Origen (ZIP o directorio)
        origin = "directory"
        zip_path = ""
        if "plugins_installed" in metadata.path:
            origin = "zip"
            try:
                from plugins.package_loader import get_package_loader
                loader = get_package_loader(os.path.dirname(self._plugins_dir or "."))
                for pkg in loader.scan():
                    if pkg.install_path == metadata.path:
                        zip_path = pkg.zip_path
                        break
            except Exception:
                pass

        # ✅ NUEVO: Cargar README
        readme_content = ""
        readme_path = ""
        try:
            from core.plugin_api.manifest_loader import get_manifest_loader
            loader = get_manifest_loader()
            readme_content, readme_path = loader.load_readme(metadata.path)
        except Exception:
            pass

        return {
            "name": plugin_name,
            "version": metadata.version,
            "description": metadata.description,
            "author": metadata.author,
            "dependencies": list(metadata.dependencies),
            "requires_debug": metadata.requires_debug,
            "enabled_by_default": metadata.enabled_by_default,
            "auto_load": metadata.auto_load,
            "path": metadata.path,
            "origin": origin,
            "zip_path": zip_path,
            "is_loaded": is_loaded,
            "is_enabled": is_enabled,
            "is_failed": is_failed,
            "capabilities": capabilities,
            "extensions": extensions,
            # ✅ NUEVO
            "readme_content": readme_content,
            "readme_path": readme_path,
            "has_readme": bool(readme_content),
        }

    def get_all_plugin_info(self) -> List[dict]:
        """Retorna info de todos los plugins (cargados o no)."""
        result = []
        for name in self._metadata.keys():
            info = self.get_plugin_info(name)
            if info:
                result.append(info)
        return result

    def get_stats(self) -> dict:
        """Stats generales para el footer."""
        return {
            "total": len(self._metadata),
            "loaded": len(self._loaded),
            "enabled": len(self._enabled),
            "failed": len(self._failed),
        }

    def install_from_zip(self, zip_path: str, copy_to_plugins: bool = True) -> tuple:
        """
        Instala un plugin desde un ZIP.

        Args:
            zip_path: ruta del .zip
            copy_to_plugins: si True, copia el ZIP a plugins/

        Returns:
            (success: bool, message: str, plugin_name: Optional[str])
        """
        try:
            from plugins.package_validator import get_package_validator
            from plugins.package_loader import get_package_loader
            import shutil

            # 1. Validar
            validator = get_package_validator()
            result = validator.validate_zip(zip_path)
            if not result.valid:
                errors = "; ".join(result.errors)
                return False, f"Validación fallida: {errors}", None

            # 2. Determinar nombre del plugin
            zip_basename = os.path.basename(zip_path)
            plugin_name = os.path.splitext(zip_basename)[0]

            # 3. Copiar a plugins/ si aplica
            target_zip = zip_path
            if copy_to_plugins and self._plugins_dir:
                target_zip = os.path.join(self._plugins_dir, zip_basename)
                if os.path.abspath(zip_path) != os.path.abspath(target_zip):
                    shutil.copy2(zip_path, target_zip)

            # 4. Extraer
            loader = get_package_loader(self._plugins_dir)
            packages = loader.scan()
            target_pkg = next(
                (p for p in packages if p.name == plugin_name),
                None,
            )
            if target_pkg is None:
                return False, f"No se encontró el paquete '{plugin_name}'", None

            if not loader._extract_package(target_pkg):
                return False, "Error extrayendo paquete", None

            # 5. Registrar en metadata (sin cargar aún)
            if plugin_name not in self._metadata:
                from .interfaces import PluginMetadata
                self._metadata[plugin_name] = PluginMetadata(
                    name=plugin_name,
                    version=target_pkg.version,
                    description=target_pkg.description,
                    path=target_pkg.install_path,
                    module_name=plugin_name,
                )
                self._stats["total_discovered"] = len(self._metadata)

            return True, f"Plugin '{plugin_name}' instalado", plugin_name

        except Exception as e:
            logger.error(f"❌ Error instalando ZIP: {e}", exc_info=True)
            return False, f"Error: {e}", None

    def uninstall(self, plugin_name: str) -> tuple:
        """
        Desinstala un plugin.

        Si es un ZIP → borra la carpeta instalada y el ZIP.
        Si es un directorio → solo desactiva (no borra archivos).

        Returns:
            (success: bool, message: str)
        """
        try:
            metadata = self._metadata.get(plugin_name)
            if metadata is None:
                return False, f"Plugin '{plugin_name}' no encontrado"

            # 1. Descargar si está cargado
            if plugin_name in self._loaded:
                self.disable(plugin_name)
                self.unload(plugin_name)

            # 2. Detectar si es ZIP
            is_zip = "plugins_installed" in metadata.path

            if is_zip:
                import shutil

                # Borrar carpeta instalada
                if os.path.isdir(metadata.path):
                    shutil.rmtree(metadata.path)
                    logger.info(f"🗑️ Carpeta eliminada: {metadata.path}")

                # Borrar ZIP original
                zip_basename = f"{plugin_name}.zip"
                zip_path = os.path.join(self._plugins_dir, zip_basename)
                if os.path.isfile(zip_path):
                    os.remove(zip_path)
                    logger.info(f"🗑️ ZIP eliminado: {zip_path}")

            # 3. Eliminar metadata
            self._metadata.pop(plugin_name, None)
            self._plugins.pop(plugin_name, None)
            self._loaded.discard(plugin_name)
            self._enabled.discard(plugin_name)
            self._failed.discard(plugin_name)

            return True, f"Plugin '{plugin_name}' desinstalado"

        except Exception as e:
            logger.error(f"❌ Error desinstalando: {e}", exc_info=True)
            return False, f"Error: {e}"

    def reload_plugin(self, plugin_name: str) -> tuple:
        """
        Recarga un plugin (unload + load + enable).

        Returns:
            (success: bool, message: str)
        """
        try:
            was_enabled = plugin_name in self._enabled

            if plugin_name in self._loaded:
                self.unload(plugin_name)

            if not self.load(plugin_name):
                return False, "Error recargando"

            if was_enabled:
                if not self.enable(plugin_name):
                    return False, "Cargado pero no activado"

            return True, f"Plugin '{plugin_name}' recargado"

        except Exception as e:
            logger.error(f"❌ Error recargando: {e}", exc_info=True)
            return False, f"Error: {e}"


# ==================== SINGLETON GLOBAL ====================

_plugin_manager: Optional[PluginManager] = None
_pm_lock = threading.Lock()


def get_plugin_manager() -> Optional[PluginManager]:
    """
    Retorna el PluginManager global (si existe).

    Returns:
        El PluginManager global o None si no se ha creado.
    """
    return _plugin_manager


def set_plugin_manager(pm: PluginManager):
    """
    Registra el PluginManager global.

    Se llama desde main.py después de crear la instancia.
    """
    global _plugin_manager
    with _pm_lock:
        _plugin_manager = pm
    logger.debug(f"🎛️ [singleton] PluginManager global registrado")