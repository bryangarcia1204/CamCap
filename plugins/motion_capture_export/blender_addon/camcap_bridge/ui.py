"""
Panel del addon en el viewport (tecla N).
"""
import bpy

from . import socket_listener


class CAMCAP_PT_main_panel(bpy.types.Panel):
    """Panel principal de CamCap Bridge"""
    bl_label = "CamCap Bridge"
    bl_idname = "CAMCAP_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "CamCap"

    def draw(self, context):
        layout = self.layout
        props = context.scene.camcap_bridge

        # ==================== Estado ====================
        box = layout.box()
        box.label(text="Estado", icon="INFO")

        if socket_listener.is_connected():
            box.label(text="🔗 Conectado", icon="LINKED")
        else:
            box.label(text="🔌 Desconectado", icon="UNLINKED")

        # Stats
        stats = socket_listener.get_stats()
        box.label(text=f"Frames: {stats['frame_count']}")
        if stats["error_count"] > 0:
            box.label(text=f"Errores: {stats['error_count']}")

        # ==================== Conexión ====================
        box = layout.box()
        box.label(text="Conexión", icon="PLUGIN")

        row = box.row(align=True)
        row.prop(props, "host", text="")
        row.prop(props, "port", text="")

        row = box.row(align=True)
        if socket_listener.is_connected():
            row.operator("camcap.disconnect", icon="CANCEL")
        else:
            row.operator("camcap.connect", icon="PLAY")

        # ==================== Aplicación ====================
        box = layout.box()
        box.label(text="Aplicación", icon="POSE_HLT")

        box.prop(props, "auto_apply")
        box.prop(props, "smooth_factor")

        row = box.row()
        row.operator("camcap.reset", icon="LOOP_BACK")

        # ==================== Ayuda ====================
        box = layout.box()
        box.label(text="Ayuda", icon="QUESTION")

        col = box.column(align=True)
        col.scale_y = 0.8
        col.label(text="1. Selecciona tu armature")
        col.label(text="2. Conecta aquí")
        col.label(text="3. En CamCap: Studio → Live")
        col.label(text="4. Pulsa 'Iniciar Live'")


classes = (
    CAMCAP_PT_main_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)