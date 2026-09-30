"""
Propiedades persistentes del addon.
"""
import bpy


class CamCapBridgeProperties(bpy.types.PropertyGroup):
    """Propiedades guardadas en la escena."""

    host: bpy.props.StringProperty(
        name="Host",
        description="Dirección de CamCap",
        default="127.0.0.1",
    )

    port: bpy.props.IntProperty(
        name="Puerto",
        description="Puerto del socket",
        default=9999,
        min=1024,
        max=65535,
    )

    connected: bpy.props.BoolProperty(
        name="Conectado",
        default=False,
    )

    auto_apply: bpy.props.BoolProperty(
        name="Aplicar automáticamente",
        description="Aplica los landmarks al rig activo al recibir cada frame",
        default=True,
    )

    smooth_factor: bpy.props.FloatProperty(
        name="Suavizado",
        description="Factor de suavizado (0 = sin suavizado, 1 = máximo)",
        default=0.3,
        min=0.0,
        max=1.0,
    )

    show_debug: bpy.props.BoolProperty(
        name="Mostrar debug",
        description="Dibuja los landmarks como puntos en el viewport",
        default=False,
    )