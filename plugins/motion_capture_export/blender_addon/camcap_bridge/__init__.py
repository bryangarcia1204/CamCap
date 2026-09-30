"""
CamCap Bridge — Addon de Blender para recibir captura de movimiento
desde CamCap en tiempo real.

Instalación:
  1. Empaqueta esta carpeta como un .zip.
  2. Blender → Edit → Preferences → Add-ons → Install.
  3. Activa "CamCap Bridge".
  4. Aparecerá un panel "CamCap Bridge" en el viewport (tecla N).

Uso:
  1. En CamCap, abre el Motion Capture Studio → modo Live.
  2. Configura host:puerto (por defecto 127.0.0.1:9999).
  3. Pulsa "📡 Iniciar Live" en CamCap.
  4. En Blender, pulsa "🔌 Conectar" en el panel.
  5. Los landmarks se aplicarán al rig activo en tiempo real.
"""
bl_info = {
    "name": "CamCap Bridge",
    "author": "CamCap",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > CamCap Bridge",
    "description": "Recibe captura de movimiento desde CamCap por socket",
    "category": "Animation",
}

import bpy

# Importar submódulos
from ...blender_addon.camcap_bridge import properties
from ...blender_addon.camcap_bridge import socket_listener
from ...blender_addon.camcap_bridge import retarget
from ...blender_addon.camcap_bridge import operators
from ...blender_addon.camcap_bridge import ui


# ============================================================
# REGISTRO
# ============================================================

classes = (
    properties.CamCapBridgeProperties,
    operators.CAMCAP_OT_connect,
    operators.CAMCAP_OT_disconnect,
    operators.CAMCAP_OT_reset,
    ui.CAMCAP_PT_main_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    # Registrar propiedades en la escena
    bpy.types.Scene.camcap_bridge = bpy.props.PointerProperty(
        type=properties.CamCapBridgeProperties
    )

    # Arrancar el listener (aunque no esté conectado)
    socket_listener.start_listener_thread()

    print("✅ CamCap Bridge: addon registrado")


def unregister():
    # Detener listener
    socket_listener.stop_listener_thread()

    # Limpiar propiedades
    if hasattr(bpy.types.Scene, "camcap_bridge"):
        del bpy.types.Scene.camcap_bridge

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    print("❌ CamCap Bridge: addon desregistrado")


if __name__ == "__main__":
    register()