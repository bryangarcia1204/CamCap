"""
PluginPackageLoader — Extrae y gestiona plugins empaquetados como .zip.

Flujo:
1. Escanea un directorio buscando .zip y carpetas.
2. Para cada .zip:
   - Calcula SHA256
   - Extrae a plugins_installed/<sha256>/
   - Si ya existe y el hash coincide → skip
   - Si el hash cambió → re-extrae
3. Retorna lista de rutas de plugins listos para cargar.

Seguridad:
- Solo extrae archivos dentro del ZIP (evita path traversal con ../)
- Limita el tamaño total (evita zip bombs)
- Filtra archivos según el manifest
"""
import os
import sys
import json
import shutil
import hashlib
import tempfile
import zipfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Set

from utils.logger import get_logger

logger = get_logger("PackageLoader")


# ============================================================
# CONSTANTES
# ============================================================

# Tamaño máximo permitido para un ZIP (10 MB por defecto)
MAX_ZIP_SIZE = 10 * 1024 * 1024

# Tamaño máximo permitido al descomprimir (50 MB)
MAX_UNCOMPRESSED_SIZE = 50 * 1024 * 1024

# Número máximo de archivos dentro de un ZIP (evita zip bombs)
MAX_FILES_IN_ZIP = 500

# Archivos obligatorios en un plugin
REQUIRED_FILES = {"plugin.py"}

# Extensiones permitidas al extraer
ALLOWED_EXTENSIONS = {
    ".py", ".pyc", ".pyi",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".txt", ".md", ".rst",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".onnx", ".tflite", ".h5", ".pkl", ".npy", ".npz",
    ".bin", ".dat", ".model", ".weights",
    ".qss", ".css", ".html",
    ".mp3", ".wav", ".ogg",
}

# Directorio donde se instalan los plugins extraídos
INSTALLED_DIR = "plugins_installed"


# ============================================================
# ERRORES
# ============================================================

class PackageError(Exception):
    """Error base de paquetes."""
    pass


class PackageInvalidError(PackageError):
    """El paquete es inválido (formato, contenido, etc.)."""
    pass


# ============================================================
# INFO DE UN PAQUETE
# ============================================================

@dataclass
class PackageInfo:
    """Info de un paquete instalado."""
    name: str                       # nombre del ZIP sin extensión
    zip_path: str                   # ruta del .zip original
    install_path: str               # ruta donde se extrajo
    sha256: str                     # hash del .zip
    version: str = "0.0.0"
    description: str = ""
    extracted: bool = False         # True si se extrajo ahora
    already_installed: bool = False # True si ya estaba extraído

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "zip_path": self.zip_path,
            "install_path": self.install_path,
            "sha256": self.sha256,
            "version": self.version,
            "description": self.description,
            "extracted": self.extracted,
            "already_installed": self.already_installed,
        }


# ============================================================
# LOADER
# ============================================================

class PluginPackageLoader:
    """Carga y extrae plugins desde .zip."""

    def __init__(self, plugins_dir: str, installed_dir: Optional[str] = None):
        """
        Args:
            plugins_dir: directorio donde están los .zip y carpetas
            installed_dir: directorio donde se extraen los .zip
        """
        self._plugins_dir = os.path.abspath(plugins_dir)
        if installed_dir is None:
            installed_dir = os.path.join(
                os.path.dirname(self._plugins_dir),
                INSTALLED_DIR
            )
        self._installed_dir = os.path.abspath(installed_dir)
        self._lock = threading.RLock()

        # Asegurar que existe el directorio de instalados
        os.makedirs(self._installed_dir, exist_ok=True)

        logger.debug(
            f"🔧 [init] PluginPackageLoader: "
            f"plugins_dir={self._plugins_dir}, "
            f"installed_dir={self._installed_dir}"
        )

    @property
    def plugins_dir(self) -> str:
        return self._plugins_dir

    @property
    def installed_dir(self) -> str:
        return self._installed_dir

    # ==================== DESCUBRIMIENTO ====================

    def scan(self) -> List[PackageInfo]:
        """
        Escanea plugins_dir buscando .zip.

        Returns:
            Lista de PackageInfo (uno por ZIP encontrado).
        """
        if not os.path.isdir(self._plugins_dir):
            logger.warning(f"⚠️ plugins_dir no existe: {self._plugins_dir}")
            return []

        results = []
        for entry in os.listdir(self._plugins_dir):
            if not entry.endswith(".zip"):
                continue

            zip_path = os.path.join(self._plugins_dir, entry)
            if not os.path.isfile(zip_path):
                continue

            try:
                info = self._analyze_zip(zip_path)
                if info is not None:
                    results.append(info)
            except PackageError as e:
                logger.error(f"❌ Paquete inválido '{entry}': {e}")
            except Exception as e:
                logger.error(f"❌ Error analizando '{entry}': {e}", exc_info=True)

        logger.info(f"📦 {len(results)} paquete(s) .zip encontrado(s)")
        return results

    def install_all(self, packages: List[PackageInfo]) -> int:
        """
        Extrae todos los paquetes.

        Returns:
            Número de paquetes extraídos.
        """
        count = 0
        for pkg in packages:
            try:
                if self._extract_package(pkg):
                    count += 1
            except Exception as e:
                logger.error(
                    f"❌ Error extrayendo '{pkg.name}': {e}",
                    exc_info=True,
                )
        return count

    # ==================== ANÁLISIS ====================

    def _analyze_zip(self, zip_path: str) -> Optional[PackageInfo]:
        """Analiza un ZIP y devuelve su info (sin extraer aún)."""
        name = os.path.basename(zip_path)[:-4]

        # Tamaño del ZIP
        zip_size = os.path.getsize(zip_path)
        if zip_size > MAX_ZIP_SIZE:
            raise PackageInvalidError(
                f"ZIP demasiado grande: {zip_size / 1024 / 1024:.1f} MB "
                f"(máx {MAX_ZIP_SIZE / 1024 / 1024:.1f} MB)"
            )

        # ✅ NUEVO: Validar con PackageValidator
        try:
            from .package_validator import get_package_validator
            validator = get_package_validator()
            result = validator.validate_zip(zip_path)
            if not result.valid:
                errors = "; ".join(result.errors)
                raise PackageInvalidError(f"Validación falló: {errors}")
            for warn in result.warnings:
                logger.warning(f"⚠️ '{name}': {warn}")
        except ImportError:
            logger.debug("⚠️ PackageValidator no disponible, saltando validación")

        # Calcular hash
        sha256 = self._compute_sha256(zip_path)

        # Verificar contenido
        with zipfile.ZipFile(zip_path, "r") as zf:
            self._validate_zip_contents(zf, name)
            manifest_data = self._read_manifest_from_zip(zf)

        install_name = f"{name}_{sha256[:8]}"
        install_path = os.path.join(self._installed_dir, install_name)

        # Ver si ya está instalado
        already_installed = False
        if os.path.isdir(install_path):
            marker = os.path.join(install_path, ".package_sha256")
            if os.path.isfile(marker):
                try:
                    with open(marker, "r") as f:
                        existing_sha = f.read().strip()
                    if existing_sha == sha256:
                        already_installed = True
                except Exception:
                    pass

        return PackageInfo(
            name=name,
            zip_path=zip_path,
            install_path=install_path,
            sha256=sha256,
            version=manifest_data.get("version", "0.0.0"),
            description=manifest_data.get("description", ""),
            extracted=False,
            already_installed=already_installed,
        )
    
    def _validate_zip_contents(self, zf: zipfile.ZipFile, name: str):
        """Valida que el ZIP tenga la estructura esperada."""
        names = zf.namelist()

        # Límite de archivos
        if len(names) > MAX_FILES_IN_ZIP:
            raise PackageInvalidError(
                f"Demasiados archivos: {len(names)} "
                f"(máx {MAX_FILES_IN_ZIP})"
            )

        # Tamaño descomprimido
        total_size = sum(info.file_size for info in zf.infolist())
        if total_size > MAX_UNCOMPRESSED_SIZE:
            raise PackageInvalidError(
                f"Tamaño descomprimido demasiado grande: "
                f"{total_size / 1024 / 1024:.1f} MB "
                f"(máx {MAX_UNCOMPRESSED_SIZE / 1024 / 1024:.1f} MB)"
            )

        # Path traversal + extensiones
        for entry in zf.infolist():
            path = entry.filename

            # Debe ser relativo
            if os.path.isabs(path):
                raise PackageInvalidError(
                    f"Path absoluto prohibido: {path}"
                )

            # Sin ../
            if ".." in path.split("/") or ".." in path.split("\\"):
                raise PackageInvalidError(
                    f"Path traversal prohibido: {path}"
                )

            # Extensión permitida
            if not entry.is_dir():
                ext = os.path.splitext(path)[1].lower()
                if ext and ext not in ALLOWED_EXTENSIONS:
                    raise PackageInvalidError(
                        f"Extensión no permitida: {path}"
                    )

        # ✅ NUEVO: Detectar carpeta contenedora
        root_folder = self._detect_root_folder(zf)
        prefix = f"{root_folder}/" if root_folder else ""

        # Archivos obligatorios
        names_set = set(n.replace("\\", "/") for n in names)
        for required in REQUIRED_FILES:
            expected_path = f"{prefix}{required}"
            # Buscar en raíz o con prefijo
            if expected_path not in names_set:
                if required not in names_set:
                    # Probar cualquier path que termine con /required
                    if not any(n.endswith(f"/{required}") for n in names_set):
                        raise PackageInvalidError(
                            f"Falta archivo obligatorio: {required} "
                            f"(buscado en raíz o '{prefix}{required}')"
                        )

    def _read_manifest_from_zip(self, zf: zipfile.ZipFile) -> dict:
        """Lee manifest.json del ZIP si existe (soporta carpeta contenedora)."""
        try:
            root_folder = self._detect_root_folder(zf)
            target_manifest = "manifest.json"
            if root_folder:
                target_manifest = f"{root_folder}/manifest.json"

            for entry in zf.namelist():
                entry_norm = entry.replace("\\", "/")
                if (entry_norm == target_manifest or
                        entry_norm == "manifest.json" or
                        entry_norm.endswith("/manifest.json")):
                    with zf.open(entry, "r") as f:
                        data = f.read()
                    manifest = json.loads(data.decode("utf-8"))
                    
                    # ✅ NUEVO: Unwrap si está envuelto en "plugins"
                    if "plugins" in manifest and isinstance(manifest["plugins"], dict):
                        plugins_dict = manifest["plugins"]
                        if len(plugins_dict) == 1:
                            inner = list(plugins_dict.values())[0]
                            if isinstance(inner, dict):
                                manifest = inner
                                logger.debug(
                                    "📋 Manifest envuelto en 'plugins' extraído"
                                )
                    
                    return manifest
        except Exception as e:
            logger.debug(f"⚠️ No se pudo leer manifest del ZIP: {e}")
        return {}

    def _detect_root_folder(self, zf: zipfile.ZipFile) -> Optional[str]:
        """
        Detecta si el ZIP tiene una carpeta contenedora única.

        Ejemplo:
            mi_plugin.zip
            └── mi_plugin/       ← carpeta contenedora
                ├── plugin.py
                └── manifest.json

        Retorna el nombre de la carpeta o None.

        Returns:
            Nombre de la carpeta (sin slash) o None si no hay contenedora.
        """
        names = zf.namelist()

        # Recolectar el primer segmento de cada path
        roots = set()
        for name in names:
            name_norm = name.replace("\\", "/")
            if not name_norm or name_norm.endswith("/"):
                continue
            parts = name_norm.split("/")
            if len(parts) > 0:
                roots.add(parts[0])

        # Si solo hay un root y coincide con un directorio en el ZIP
        if len(roots) == 1:
            root = roots.pop()
            # Verificar que sea una carpeta (tiene subpaths)
            for name in names:
                name_norm = name.replace("\\", "/")
                if name_norm.startswith(f"{root}/"):
                    logger.debug(
                        f"📦 [root] Carpeta contenedora detectada: '{root}'"
                    )
                    return root

        return None

    # ==================== EXTRACCIÓN ====================

    def _extract_package(self, pkg: PackageInfo) -> bool:
        """
        Extrae un paquete a su install_path.

        Returns:
            True si se extrajo (o ya estaba), False si falló.
        """
        if pkg.already_installed:
            logger.debug(f"⏭️ Paquete '{pkg.name}' ya extraído, skip")
            pkg.extracted = False
            return True

        logger.info(
            f"📦 Extrayendo '{pkg.name}' → {pkg.install_path}"
        )

        # Limpiar si existe (hash cambió)
        if os.path.isdir(pkg.install_path):
            logger.debug(
                f"🗑️ Eliminando versión antigua de '{pkg.name}'"
            )
            try:
                shutil.rmtree(pkg.install_path)
            except Exception as e:
                logger.error(f"❌ No se pudo borrar: {e}")
                return False

        # Extraer a temp y mover (extracción atómica)
        temp_dir = tempfile.mkdtemp(prefix=f"procamara_pkg_{pkg.name}_")
        try:
            with zipfile.ZipFile(pkg.zip_path, "r") as zf:
                self._safe_extract(zf, temp_dir)

            # Mover temp_dir → install_path
            os.makedirs(os.path.dirname(pkg.install_path), exist_ok=True)
            if os.path.exists(pkg.install_path):
                shutil.rmtree(pkg.install_path)
            shutil.move(temp_dir, pkg.install_path)
            temp_dir = None   # ya se movió

            # Escribir marker con el hash
            marker = os.path.join(pkg.install_path, ".package_sha256")
            with open(marker, "w") as f:
                f.write(pkg.sha256)

            pkg.extracted = True
            pkg.already_installed = True
            logger.info(f"✅ Paquete '{pkg.name}' extraído correctamente")
            return True

        except Exception as e:
            logger.error(
                f"❌ Error extrayendo '{pkg.name}': {e}", exc_info=True
            )
            return False

        finally:
            if temp_dir is not None and os.path.isdir(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass

    def _safe_extract(self, zf: zipfile.ZipFile, target_dir: str):
        """
        Extrae respetando validaciones. Si el ZIP tiene una carpeta
        contenedora única, la aplana.
        """
        root_folder = self._detect_root_folder(zf)

        for entry in zf.infolist():
            original_name = entry.filename
            name_norm = original_name.replace("\\", "/")

            # Aplanar si hay root folder
            if root_folder:
                prefix = f"{root_folder}/"
                if name_norm.startswith(prefix):
                    new_name = name_norm[len(prefix):]
                elif name_norm == root_folder:
                    # Es la carpeta misma, saltar
                    continue
                else:
                    # Archivo fuera del root, mantener
                    new_name = name_norm
            else:
                new_name = name_norm

            if not new_name:
                continue

            # Construir path destino
            target_path = os.path.join(target_dir, new_name)

            # Verificación anti path-traversal
            target_path_real = os.path.realpath(target_path)
            target_dir_real = os.path.realpath(target_dir)
            if not target_path_real.startswith(target_dir_real):
                raise PackageInvalidError(
                    f"Path traversal detectado: {original_name}"
                )

            # Crear directorio si es necesario
            if entry.is_dir():
                os.makedirs(target_path, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                with zf.open(entry, "r") as src:
                    with open(target_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)

            if root_folder and name_norm.startswith(f"{root_folder}/"):
                logger.debug(
                    f"📦 [extract] Aplanado: '{original_name}' → '{new_name}'"
                )

    # ==================== UTILIDADES ====================

    def _compute_sha256(self, file_path: str) -> str:
        """Calcula SHA256 de un archivo."""
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def cleanup_orphans(self, valid_install_paths: Set[str]):
        """
        Elimina directorios en installed_dir que ya no tienen ZIP asociado.

        Args:
            valid_install_paths: conjunto de paths válidos (mantener).
        """
        if not os.path.isdir(self._installed_dir):
            return

        removed = 0
        for entry in os.listdir(self._installed_dir):
            entry_path = os.path.join(self._installed_dir, entry)
            if not os.path.isdir(entry_path):
                continue
            if entry_path not in valid_install_paths:
                try:
                    shutil.rmtree(entry_path)
                    removed += 1
                    logger.debug(f"🗑️ Orphan eliminado: {entry}")
                except Exception as e:
                    logger.warning(f"⚠️ No se pudo eliminar '{entry}': {e}")

        if removed:
            logger.info(f"🗑️ {removed} paquete(s) huérfano(s) eliminado(s)")


# ============================================================
# SINGLETON
# ============================================================

_loader: Optional[PluginPackageLoader] = None
_lock = threading.Lock()


def get_package_loader(
    plugins_dir: str, installed_dir: Optional[str] = None
) -> PluginPackageLoader:
    """Obtiene el singleton."""
    global _loader
    with _lock:
        if _loader is None or _loader.plugins_dir != os.path.abspath(plugins_dir):
            _loader = PluginPackageLoader(plugins_dir, installed_dir)
    return _loader