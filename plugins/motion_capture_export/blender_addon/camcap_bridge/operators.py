"""
Operadores de Blender para controlar el bridge.

Cada operador corre en el hilo principal de Blender.
"""
import bpy

from . import socket_listener


class CAMCAP_OT_connect(bpy.types.Operator):
    """Conecta a CamCap por socket"""
    bl_idname = "camcap.connect"
    bl_label = "Conectar"
    bl_description = "Conecta a CamCap para recibir captura de movimiento"

    def execute(self, context):
        props = context.scene.camcap_bridge

        if socket_listener.is_connected():
            self.report({"INFO"}, "Ya está conectado")
            return {"FINISHED"}

        # Iniciar conexión (asíncrona, el listener maneja el resto)
        socket_listener.connect(
            host=props.host,
            port=props.port,
            on_connected=self._on_connected,
            on_disconnected=self._on_disconnected,
        )

        self.report({"INFO"}, f"Conectando a {props.host}:{props.port}...")
        return {"FINISHED"}

    def _on_connected(self, address):
        """Callback cuando el socket se conecta."""
        # Actualizar propiedad (esto se hace desde el thread del listener,
        # por lo que hay que usar timer para el hilo principal)
        import bpy

        def _update():
            try:
                bpy.context.scene.camcap_bridge.connected = True
            except Exception:
                pass
            return None  # No repetir

        bpy.app.timers.register(_update)

    def _on_disconnected(self, address):
        """Callback cuando el socket se desconecta."""
        import bpy

        def _update():
            try:
                bpy.context.scene.camcap_bridge.connected = False
            except Exception:
                pass
            return None

        bpy.app.timers.register(_update)


class CAMCAP_OT_disconnect(bpy.types.Operator):
    """Desconecta de CamCap"""
    bl_idname = "camcap.disconnect"
    bl_label = "Desconectar"
    bl_description = "Cierra la conexión con CamCap"

    def execute(self, context):
        socket_listener.disconnect()
        context.scene.camcap_bridge.connected = False
        self.report({"INFO"}, "Desconectado")
        return {"FINISHED"}


class CAMCAP_OT_reset(bpy.types.Operator):
    """Resetea el armature activo a su rest pose"""
    bl_idname = "camcap.reset"
    bl_label = "Resetear pose"
    bl_description = "Limpia todas las rotaciones del armature activo"

    def execute(self, context):
        armature = context.active_object
        if armature is None or armature.type != "ARMATURE":
            self.report({"ERROR"}, "Selecciona un armature primero")
            return {"CANCELLED"}

        from . import retarget
        retarget.reset_armature(armature)

        self.report({"INFO"}, f"Pose reseteada: {armature.name}")
        return {"FINISHED"}


# ============================================================
# TIMER QUE APLICA LOS FRAMES
# ============================================================

def _apply_frames_timer():
    """
    Timer que corre en el hilo principal de Blender.
    Lee el último frame del listener y lo aplica al rig activo.
    """
    try:
        import bpy

        # Verificar que el addon está activo
        if not hasattr(bpy.types.Scene, "camcap_bridge"):
            return 0.05  # 50ms

        props = bpy.context.scene.camcap_bridge

        if not props.auto_apply:
            return 0.05

        if not socket_listener.is_connected():
            return 0.05

        # Obtener el último frame
        frame = socket_listener.get_last_frame()
        if frame is None:
            return 0.05

        # Obtener el armature activo
        armature = bpy.context.active_object
        if armature is None or armature.type != "ARMATURE":
            return 0.05

        # Aplicar el frame
        from . import retarget
        retarget.apply_frame_to_armature(
            frame=frame,
            armature_obj=armature,
            smooth_factor=props.smooth_factor,
        )

        # Forzar redibujado
        if bpy.context.screen:
            for area in bpy.context.screen.areas:
                if area.type == "VIEW_3D":
                    area.tag_redraw()

    except Exception as e:
        print(f"⚠️ CamCap Bridge: error en timer: {e}")

    return 0.05  # 50ms → 20 fps


# Registrar el timer al arrancar el addon
import bpy
if not bpy.app.timers.is_registered(_apply_frames_timer):
    bpy.app.timers.register(_apply_frames_timer, persistent=True)


# ============================================================
# REGISTRO DE CLASES
# ============================================================

classes = (
    CAMCAP_OT_connect,
    CAMCAP_OT_disconnect,
    CAMCAP_OT_reset,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)