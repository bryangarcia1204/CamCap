"""
Cargador de manifests con soporte de auto-registro.

Estrategia:
  1. Cada plugin puede tener su propio manifest.json en su carpeta.
  2. El manifest global (plugins/manifest.json) es opcional y sirve
     como override/complemento.
  3. Los campos del manifest local tienen prioridad sobre el global.
  4. Si un plugin no tiene manifest local, se usan los defaults.

También carga el README.md del plugin si existe, para mostrarlo en
el diálogo de info del GUI manager.
"""
import os
import json
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

from utils.logger import get_logger

logger = get_logger("Plugin.ManifestLoader")


# ============================================================
# DEFAULTS
# ============================================================

DEFAULT_MANIFEST = {
    "version": "0.0.0",
    "description": "",
    "author": "",
    "dependencies": [],
    "capabilities": [],
    "enabled_by_default": True,
    "auto_load": True,
    "requires_debug": False,
}


# ============================================================
# DATA CLASS
# ============================================================

@dataclass
class LoadedManifest:
    """Resultado del merge de manifest local + global + defaults."""
    name: str
    version: str = "0.0.0"
    description: str = ""
    author: str = ""
    dependencies: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    enabled_by_default: bool = True
    auto_load: bool = True
    requires_debug: bool = False

    # Extras (no van al PluginMetadata pero útiles para la UI)
    readme_content: str = ""
    readme_path: str = ""
    source: str = ""           # "local", "global", "default"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "dependencies": list(self.dependencies),
            "capabilities": list(self.capabilities),
            "enabled_by_default": self.enabled_by_default,
            "auto_load": self.auto_load,
            "requires_debug": self.requires_debug,
            "source": self.source,
        }


# ============================================================
# LOADER
# ============================================================

class ManifestLoader:
    """
    Carga manifests de plugins con merge local/global/defaults.

    Uso:
        loader = ManifestLoader()
        loader.load_global("plugins/manifest.json")
        manifest = loader.resolve("audio", "plugins/audio/")
    """

    # Nombres de archivos soportados
    MANIFEST_NAMES = ("manifest.json", "plugin.json", "info.json")
    README_NAMES = ("README.md", "readme.md", "Readme.md", "README.MD")

    # Clave donde el manifest global envuelve la info de cada plugin
    GLOBAL_WRAPPER_KEY = "plugins"

    def __init__(self):
        self._global_plugins: Dict[str, Dict[str, Any]] = {}
        self._global_loaded = False

    # ==================== GLOBAL ====================

    def load_global(self, manifest_path: str) -> bool:
        """
        Carga el manifest global. Formato esperado:

            {
              "plugins": {
                "audio": {
                  "version": "1.0.0",
                  "enabled_by_default": true,
                  ...
                },
                ...
              }
            }

        También acepta un manifest sin wrapper (cada key es un plugin).
        """
        if not os.path.isfile(manifest_path):
            logger.debug(f"Manifest global no existe: {manifest_path}")
            return False

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Soportar con y sin wrapper
            if self.GLOBAL_WRAPPER_KEY in data and isinstance(data[self.GLOBAL_WRAPPER_KEY], dict):
                plugins_dict = data[self.GLOBAL_WRAPPER_KEY]
            else:
                plugins_dict = data

            self._global_plugins = {}
            for name, cfg in plugins_dict.items():
                if isinstance(cfg, dict):
                    self._global_plugins[name] = cfg

            self._global_loaded = True
            logger.info(
                f"📋 Manifest global cargado: "
                f"{len(self._global_plugins)} plugin(s) declarado(s)"
            )
            return True

        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON inválido en {manifest_path}: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Error leyendo manifest global: {e}", exc_info=True)
            return False

    def get_global_config(self, plugin_name: str) -> Dict[str, Any]:
        """Retorna el config global de un plugin (o {} si no existe)."""
        return dict(self._global_plugins.get(plugin_name, {}))

    # ==================== LOCAL ====================

    def load_local(self, plugin_dir: str) -> Optional[Dict[str, Any]]:
        """
        Busca y carga el manifest local de un plugin.

        Busca en este orden:
          <plugin_dir>/manifest.json
          <plugin_dir>/plugin.json
          <plugin_dir>/info.json

        Returns:
            Dict con el manifest, o None si no existe/está corrupto.
        """
        for name in self.MANIFEST_NAMES:
            path = os.path.join(plugin_dir, name)
            if os.path.isfile(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    # Soportar manifest envuelto en "plugins"
                    if (self.GLOBAL_WRAPPER_KEY in data
                            and isinstance(data[self.GLOBAL_WRAPPER_KEY], dict)):
                        # Puede haber 1 o varios plugins dentro
                        inner = data[self.GLOBAL_WRAPPER_KEY]
                        if len(inner) == 1:
                            data = list(inner.values())[0]
                        else:
                            # Si hay varios, usar el que coincida con el nombre de la carpeta
                            dir_name = os.path.basename(plugin_dir.rstrip("/\\"))
                            if dir_name in inner:
                                data = inner[dir_name]
                            else:
                                data = list(inner.values())[0]

                    logger.debug(f"📋 Manifest local cargado: {path}")
                    return data

                except json.JSONDecodeError as e:
                    logger.warning(f"⚠️ JSON inválido en {path}: {e}")
                except Exception as e:
                    logger.warning(f"⚠️ Error leyendo {path}: {e}")

        return None

    # ==================== README ====================

    def load_readme(self, plugin_dir: str) -> tuple:
        """
        Busca y carga el README del plugin.

        Returns:
            (readme_content, readme_path) o ("", "") si no existe.
        """
        for name in self.README_NAMES:
            path = os.path.join(plugin_dir, name)
            if os.path.isfile(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()
                    logger.debug(f"📖 README cargado: {path}")
                    return content, path
                except Exception as e:
                    logger.warning(f"⚠️ Error leyendo README {path}: {e}")

        return "", ""

    # ==================== RESOLVE ====================

    def resolve(
        self,
        plugin_name: str,
        plugin_dir: str,
        prefer_local: bool = True,
    ) -> LoadedManifest:
        """
        Resuelve el manifest final de un plugin.

        Orden de precedencia (si prefer_local=True):
          1. Local (<plugin_dir>/manifest.json)
          2. Global (plugins/manifest.json → plugins.<name>)
          3. Defaults

        Si prefer_local=False, el global overridea al local.

        Returns:
            LoadedManifest con todos los campos resueltos.
        """
        local = self.load_local(plugin_dir) if plugin_dir else None
        global_cfg = self.get_global_config(plugin_name)

        sources = []
        if local:
            sources.append("local")
        if global_cfg:
            sources.append("global")
        if not sources:
            sources.append("default")

        # Base: defaults
        merged = dict(DEFAULT_MANIFEST)

        # Aplicar global
        if global_cfg:
            for k, v in global_cfg.items():
                if v is not None:
                    merged[k] = v

        # Aplicar local
        if local:
            for k, v in local.items():
                if v is not None:
                    merged[k] = v

        # Cargar README (siempre local)
        readme_content, readme_path = self.load_readme(plugin_dir) if plugin_dir else ("", "")

        return LoadedManifest(
            name=plugin_name,
            version=merged.get("version", "0.0.0"),
            description=merged.get("description", ""),
            author=merged.get("author", ""),
            dependencies=list(merged.get("dependencies", [])),
            capabilities=list(merged.get("capabilities", [])),
            enabled_by_default=bool(merged.get("enabled_by_default", True)),
            auto_load=bool(merged.get("auto_load", True)),
            requires_debug=bool(merged.get("requires_debug", False)),
            readme_content=readme_content,
            readme_path=readme_path,
            source="+".join(sources),
        )


# ============================================================
# SINGLETON
# ============================================================

_loader: Optional[ManifestLoader] = None


def get_manifest_loader() -> ManifestLoader:
    """Obtiene el loader global."""
    global _loader
    if _loader is None:
        _loader = ManifestLoader()
    return _loader


def set_manifest_loader(loader: ManifestLoader):
    """Reemplaza el loader (para tests)."""
    global _loader
    _loader = loader