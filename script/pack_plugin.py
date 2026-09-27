"""
Script para empaquetar un plugin como .zip.

Uso:
    python scripts/pack_plugin.py plugins/motion_detector
    python scripts/pack_plugin.py plugins/motion_detector -o dist/motion_detector.zip
"""
import os
import sys
import json
import zipfile
import argparse
from pathlib import Path


def pack_plugin(plugin_dir: str, output_zip: str = None) -> bool:
    """Empaqueta un directorio de plugin como ZIP."""
    plugin_path = Path(plugin_dir).resolve()

    if not plugin_path.is_dir():
        print(f"❌ No es un directorio: {plugin_path}")
        return False

    if not (plugin_path / "plugin.py").is_file():
        print(f"❌ Falta plugin.py en {plugin_path}")
        return False

    plugin_name = plugin_path.name

    if output_zip is None:
        output_zip = f"{plugin_name}.zip"

    print(f"📦 Empaquetando '{plugin_name}' → {output_zip}")

    # Archivos/carpetas a excluir
    EXCLUDE = {
        "__pycache__", ".pyc", ".pyo", ".git",
        ".vscode", ".idea", ".DS_Store", "Thumbs.db",
    }

    count = 0
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(plugin_path):
            # Filtrar directorios
            dirs[:] = [d for d in dirs if d not in EXCLUDE]

            for fname in files:
                if fname.endswith((".pyc", ".pyo")):
                    continue
                if fname in EXCLUDE:
                    continue

                fpath = Path(root) / fname
                arcname = fpath.relative_to(plugin_path)

                # ✅ IMPORTANTE: usar el nombre del plugin como prefijo
                zf.write(fpath, arcname)
                count += 1
                print(f"  + {arcname}")

    size_kb = os.path.getsize(output_zip) / 1024
    print(f"\n✅ {count} archivos empaquetados")
    print(f"✅ ZIP: {output_zip} ({size_kb:.1f} KB)")

    # Sugerir carpeta contenedora correcta
    print(f"\n💡 El ZIP contiene los archivos en la RAÍZ.")
    print(f"   Estructura esperada:")
    print(f"   {plugin_name}.zip")
    print(f"   ├── plugin.py")
    print(f"   ├── manifest.json")
    print(f"   └── ...")

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Empaqueta un plugin como .zip"
    )
    parser.add_argument(
        "plugin_dir",
        help="Directorio del plugin (ej: plugins/motion_detector)"
    )
    parser.add_argument(
        "-o", "--output",
        help="Archivo ZIP de salida (default: <nombre>.zip)"
    )

    args = parser.parse_args()

    success = pack_plugin(args.plugin_dir, args.output)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()