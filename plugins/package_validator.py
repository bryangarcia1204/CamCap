"""
Validación de paquetes de plugins.

Verifica:
- Estructura del ZIP
- Contenido del manifest
- Código Python (AST básico)
- Tamaños
"""
import os
import ast
import json
import zipfile
import hashlib
import threading
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Set, Tuple
from pathlib import Path

from utils.logger import get_logger

logger = get_logger("PackageValidator")


# ============================================================
# RESULTADO DE VALIDACIÓN
# ============================================================

@dataclass
class ValidationResult:
    """Resultado de una validación."""
    valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    info: Dict = field(default_factory=dict)

    def add_error(self, msg: str):
        self.valid = False
        self.errors.append(msg)

    def add_warning(self, msg: str):
        self.warnings.append(msg)

    def __repr__(self):
        status = "✅" if self.valid else "❌"
        return (
            f"ValidationResult({status} "
            f"errors={len(self.errors)}, warnings={len(self.warnings)})"
        )


# ============================================================
# VALIDATOR
# ============================================================

class PackageValidator:
    """Valida paquetes de plugins."""

    # Imports prohibidos en código de plugins
    FORBIDDEN_IMPORTS = {
        "ctypes",
        "cffi",
        "mmap",
        "fcntl",
    }

    # Módulos que requieren capability (validación de manifest)
    CAPABILITY_MODULES = {
        "socket": "network",
        "requests": "network",
        "urllib": "network",
        "http": "network",
        "subprocess": "process_execution",
        "sqlite3": "write_files",
        "shutil": "file_delete",
    }

    # Manifest keys requeridas
    REQUIRED_MANIFEST_KEYS = {"version"}

    # Manifest keys opcionales
    OPTIONAL_MANIFEST_KEYS = {
        "description", "author", "dependencies",
        "capabilities", "enabled_by_default",
        "auto_load", "requires_debug", "name",
    }

    def __init__(self):
        self._lock = threading.RLock()

    # ==================== API ====================

    def validate_zip(self, zip_path: str) -> ValidationResult:
        """Valida un ZIP completo."""
        result = ValidationResult()

        if not os.path.isfile(zip_path):
            result.add_error(f"Archivo no existe: {zip_path}")
            return result

        if not zipfile.is_zipfile(zip_path):
            result.add_error("No es un archivo ZIP válido")
            return result

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                # 1. Estructura
                self._validate_structure(zf, result)

                # 2. Manifest
                manifest = self._validate_manifest(zf, result)

                # 3. Código Python
                if manifest:
                    self._validate_python_code(zf, manifest, result)

                # 4. Capabilities vs imports
                if manifest:
                    self._validate_capabilities(manifest, zf, result)

                # 5. Info adicional
                result.info["manifest"] = manifest
                result.info["zip_size"] = os.path.getsize(zip_path)
                result.info["file_count"] = len(zf.namelist())

        except Exception as e:
            result.add_error(f"Error validando ZIP: {e}")

        return result

    def validate_directory(self, dir_path: str) -> ValidationResult:
        """Valida un directorio de plugin (sin ZIP)."""
        result = ValidationResult()

        if not os.path.isdir(dir_path):
            result.add_error(f"Directorio no existe: {dir_path}")
            return result

        # Manifest
        manifest_path = os.path.join(dir_path, "manifest.json")
        manifest = {}
        if os.path.isfile(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
            except Exception as e:
                result.add_error(f"Error leyendo manifest: {e}")
        else:
            result.add_warning("Sin manifest.json")

        # Validar manifest
        self._validate_manifest_dict(manifest, result)

        # Validar código Python
        for root, dirs, files in os.walk(dir_path):
            for fname in files:
                if fname.endswith(".py"):
                    fpath = os.path.join(root, fname)
                    self._validate_python_file(fpath, result)

        result.info["manifest"] = manifest
        return result

    # ==================== VALIDACIONES ====================

    def _validate_structure(self, zf: zipfile.ZipFile, result: ValidationResult):
        """Valida estructura del ZIP."""
        names = zf.namelist()

        # Al menos plugin.py
        if not any(
            n.endswith("plugin.py") or n == "plugin.py"
            for n in names
        ):
            result.add_error("Falta archivo 'plugin.py'")

        # Sin path traversal
        for name in names:
            if ".." in name.split("/"):
                result.add_error(f"Path traversal: {name}")

    def _validate_manifest(self, zf: zipfile.ZipFile,
                          result: ValidationResult) -> dict:
        """Lee y valida el manifest.json del ZIP."""
        manifest = {}
        try:
            for entry in zf.namelist():
                entry_norm = entry.replace("\\", "/")
                if entry_norm == "manifest.json" or entry_norm.endswith("/manifest.json"):
                    with zf.open(entry, "r") as f:
                        data = f.read()
                    manifest = json.loads(data.decode("utf-8"))
                    break
        except json.JSONDecodeError as e:
            result.add_error(f"manifest.json inválido: {e}")
            return {}
        except Exception as e:
            result.add_warning(f"No se pudo leer manifest: {e}")
            return {}

        if not manifest:
            result.add_warning("Sin manifest.json (se usarán defaults)")
            return {}

        self._validate_manifest_dict(manifest, result)
        return manifest

    def _validate_manifest_dict(self, manifest: dict, result: ValidationResult):
        """Valida el contenido de un manifest."""
        # ✅ NUEVO: Soportar manifest envuelto en "plugins" (formato global)

        if "plugins" in manifest and isinstance(manifest["plugins"], dict):
            # Extraer el primer plugin si solo hay uno
            plugins_dict = manifest["plugins"]
            if len(plugins_dict) == 1:
                # Es un manifest envuelto, extraer el plugin
                inner_manifest = list(plugins_dict.values())[0]
                if isinstance(inner_manifest, dict):
                    manifest.clear()
                    manifest.update(inner_manifest)
                    result.add_warning(
                        "Manifest envuelto en 'plugins' extraído automáticamente"
                    )

        # Keys requeridas
        for key in self.REQUIRED_MANIFEST_KEYS:
            if key not in manifest:
                result.add_error(f"Manifest: falta '{key}'")

        # Keys desconocidas
        known_keys = self.REQUIRED_MANIFEST_KEYS | self.OPTIONAL_MANIFEST_KEYS
        for key in manifest.keys():
            if key not in known_keys:
                result.add_warning(f"Manifest: key desconocida '{key}'")

        # Tipos
        if "version" in manifest and not isinstance(manifest["version"], str):
            result.add_error("Manifest: 'version' debe ser string")

        if "capabilities" in manifest:
            if not isinstance(manifest["capabilities"], list):
                result.add_error("Manifest: 'capabilities' debe ser lista")
            else:
                for cap in manifest["capabilities"]:
                    if not isinstance(cap, str):
                        result.add_error(
                            f"Manifest: capability '{cap}' debe ser string"
                        )

        if "dependencies" in manifest:
            if not isinstance(manifest["dependencies"], list):
                result.add_error("Manifest: 'dependencies' debe ser lista")

    def _validate_python_code(self, zf: zipfile.ZipFile, manifest: dict,
                             result: ValidationResult):
        """Valida el código Python dentro del ZIP."""
        for entry in zf.namelist():
            if not entry.endswith(".py"):
                continue
            try:
                with zf.open(entry, "r") as f:
                    code = f.read().decode("utf-8")
                self._validate_python_source(code, entry, result)
            except Exception as e:
                result.add_warning(f"No se pudo leer '{entry}': {e}")

    def _validate_python_file(self, file_path: str, result: ValidationResult):
        """Valida un archivo Python en disco."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                code = f.read()
            self._validate_python_source(
                code, os.path.basename(file_path), result
            )
        except Exception as e:
            result.add_warning(f"No se pudo leer '{file_path}': {e}")

    def _validate_python_source(self, source: str, filename: str,
                                result: ValidationResult):
        """Valida el código Python usando AST."""
        try:
            tree = ast.parse(source, filename=filename)
        except SyntaxError as e:
            result.add_error(f"Sintaxis inválida en '{filename}': {e}")
            return

        for node in ast.walk(tree):
            # Imports prohibidos
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root in self.FORBIDDEN_IMPORTS:
                        result.add_error(
                            f"'{filename}': import prohibido '{alias.name}'"
                        )

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root = node.module.split(".")[0]
                    if root in self.FORBIDDEN_IMPORTS:
                        result.add_error(
                            f"'{filename}': import prohibido '{node.module}'"
                        )

            # exec() / eval()
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in ("exec", "eval"):
                        result.add_warning(
                            f"'{filename}': uso de {node.func.id}()"
                        )

    def _validate_capabilities(self, manifest: dict, zf: zipfile.ZipFile,
                              result: ValidationResult):
        """
        Verifica que las capabilities declaradas cubran los imports sensibles.
        """
        declared_caps = set(manifest.get("capabilities", []))

        # Recolectar imports del código
        imported_modules: Set[str] = set()
        for entry in zf.namelist():
            if not entry.endswith(".py"):
                continue
            try:
                with zf.open(entry, "r") as f:
                    code = f.read().decode("utf-8")
                tree = ast.parse(code, filename=entry)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            imported_modules.add(alias.name.split(".")[0])
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            imported_modules.add(node.module.split(".")[0])
            except Exception:
                pass

        # Verificar
        for mod in imported_modules:
            required_cap = self.CAPABILITY_MODULES.get(mod)
            if required_cap and required_cap not in declared_caps:
                result.add_error(
                    f"Import '{mod}' requiere capability "
                    f"'{required_cap}' (no declarada)"
                )


# ============================================================
# SINGLETON
# ============================================================

_validator: Optional[PackageValidator] = None
_lock = threading.Lock()


def get_package_validator() -> PackageValidator:
    """Obtiene el singleton."""
    global _validator
    with _lock:
        if _validator is None:
            _validator = PackageValidator()
    return _validator