"""
Aplicación de landmarks al rig activo.

IMPORTANTE: Este módulo SOLO debe ser llamado desde el hilo principal
de Blender (por ejemplo, desde bpy.app.timers). NO desde el hilo
del socket listener.

Estrategia:
  - Mapea los 33 landmarks de MediaPipe a los huesos de un rig
    estándar (Rigify, Mixamo, MakeHuman).
  - Aplica las rotaciones mínimas necesarias para orientar cada hueso
    hacia su landmark correspondiente.
  - Suaviza las rotaciones entre frames para evitar jitter.
"""
import math
from typing import Optional, Dict, Any, List

import bpy
from mathutils import Vector, Quaternion, Matrix

# ============================================================
# MAPEO LANDMARKS → HUESOS
# ============================================================

# Índices de MediaPipe Pose
LM = {
    "nose": 0,
    "left_eye_inner": 1, "left_eye": 2, "left_eye_outer": 3,
    "right_eye_inner": 4, "right_eye": 5, "right_eye_outer": 6,
    "left_ear": 7, "right_ear": 8,
    "mouth_left": 9, "mouth_right": 10,
    "left_shoulder": 11, "right_shoulder": 12,
    "left_elbow": 13, "right_elbow": 14,
    "left_wrist": 15, "right_wrist": 16,
    "left_pinky": 17, "right_pinky": 18,
    "left_index": 19, "right_index": 20,
    "left_thumb": 21, "right_thumb": 22,
    "left_hip": 23, "right_hip": 24,
    "left_knee": 25, "right_knee": 26,
    "left_ankle": 27, "right_ankle": 28,
    "left_heel": 29, "right_heel": 30,
    "left_foot_index": 31, "right_foot_index": 32,
}


# Mapeo estándar hueso → (landmark_origen, landmark_destino)
# Este mapeo funciona con Rigify, Mixamo y MakeHuman porque
# los nombres de huesos son muy similares.
BONE_LANDMARK_MAP = {
    # Torso (Rigify / Mixamo)
    "spine":        ("left_hip",       "left_shoulder"),
    "spine.001":    ("left_hip",       "left_shoulder"),
    "spine.002":    ("left_hip",       "left_shoulder"),
    "spine.003":    ("left_hip",       "left_shoulder"),
    "spine.004":    ("neck",           "head"),
    "chest":        ("hips_center",    "chest_center"),
    "neck":         ("chest_center",   "head"),

    # Brazo izquierdo
    "shoulder.L":   ("chest_center",   "left_shoulder"),
    "upper_arm.L":  ("left_shoulder",  "left_elbow"),
    "forearm.L":    ("left_elbow",     "left_wrist"),
    "hand.L":       ("left_wrist",     "left_index"),

    # Brazo derecho
    "shoulder.R":   ("chest_center",   "right_shoulder"),
    "upper_arm.R":  ("right_shoulder", "right_elbow"),
    "forearm.R":    ("right_elbow",    "right_wrist"),
    "hand.R":       ("right_wrist",    "right_index"),

    # Pierna izquierda
    "thigh.L":      ("left_hip",       "left_knee"),
    "shin.L":       ("left_knee",      "left_ankle"),
    "foot.L":       ("left_ankle",     "left_foot_index"),
    "toe.L":        ("left_foot_index","left_foot_index"),

    # Pierna derecha
    "thigh.R":      ("right_hip",      "right_knee"),
    "shin.R":       ("right_knee",     "right_ankle"),
    "foot.R":       ("right_ankle",    "right_foot_index"),
    "toe.R":        ("right_foot_index","right_foot_index"),

    # Huesos de Rigify que no se mapean (se dejan como están)
    # "pelvis", "root", "torso"
}


# ============================================================
# ESTADO INTERNO (para suavizado)
# ============================================================

_last_quaternions: Dict[str, Quaternion] = {}


# ============================================================
# API PÚBLICA
# ============================================================

def apply_frame_to_armature(
    frame: Dict[str, Any],
    armature_obj: bpy.types.Object,
    smooth_factor: float = 0.3,
) -> bool:
    """
    Aplica un frame de landmarks al armature dado.

    Args:
        frame: dict con type="frame" y person.landmarks (33 puntos).
        armature_obj: objeto armature de Blender.
        smooth_factor: 0 = sin suavizado, 1 = máximo.

    Returns:
        True si se aplicó correctamente.
    """
    if armature_obj is None or armature_obj.type != "ARMATURE":
        return False

    person = frame.get("person")
    if person is None:
        return False

    landmarks = person.get("landmarks")
    if not landmarks or len(landmarks) < 33:
        return False

    # Convertir a dict de nombres
    lms = _landmarks_to_dict(landmarks)

    # Calcular puntos virtuales
    pts = _compute_virtual_points(lms)

    # Aplicar al armature
    _apply_to_bones(armature_obj, pts, smooth_factor)

    return True


def reset_armature(armature_obj: bpy.types.Object):
    """Limpia todas las rotaciones del armature (vuelve a rest pose)."""
    if armature_obj is None or armature_obj.type != "ARMATURE":
        return

    _last_quaternions.clear()

    for pose_bone in armature_obj.pose.bones:
        pose_bone.rotation_mode = "QUATERNION"
        pose_bone.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        pose_bone.location = (0.0, 0.0, 0.0)
        pose_bone.scale = (1.0, 1.0, 1.0)


# ============================================================
# HELPERS
# ============================================================

def _landmarks_to_dict(landmarks: List[List[float]]) -> Dict[str, List[float]]:
    """Convierte la lista de 33 landmarks a dict con nombres."""
    return {
        name: landmarks[idx]
        for name, idx in LM.items()
        if idx < len(landmarks)
    }


def _compute_virtual_points(lms: Dict[str, List[float]]) -> Dict[str, Vector]:
    """Calcula puntos virtuales como Vector de Blender."""
    def get(name: str) -> Vector:
        if name in lms:
            return Vector(lms[name][:3])
        return Vector((0.0, 0.0, 0.0))

    left_hip = get("left_hip")
    right_hip = get("right_hip")
    left_shoulder = get("left_shoulder")
    right_shoulder = get("right_shoulder")
    nose = get("nose")

    hips_center = (left_hip + right_hip) * 0.5
    chest_center = (left_shoulder + right_shoulder) * 0.5
    neck_center = chest_center + Vector((0.0, -0.05, 0.0))

    return {
        "hips_center": hips_center,
        "chest_center": chest_center,
        "neck_center": neck_center,
        "head": nose,
        "left_hip": left_hip,
        "right_hip": right_hip,
        "left_shoulder": left_shoulder,
        "right_shoulder": right_shoulder,
        "left_elbow": get("left_elbow"),
        "right_elbow": get("right_elbow"),
        "left_wrist": get("left_wrist"),
        "right_wrist": get("right_wrist"),
        "left_index": get("left_index"),
        "right_index": get("right_index"),
        "left_knee": get("left_knee"),
        "right_knee": get("right_knee"),
        "left_ankle": get("left_ankle"),
        "right_ankle": get("right_ankle"),
        "left_foot_index": get("left_foot_index"),
        "right_foot_index": get("right_foot_index"),
    }


def _apply_to_bones(
    armature_obj: bpy.types.Object,
    pts: Dict[str, Vector],
    smooth_factor: float,
):
    """Aplica rotaciones a los huesos del armature."""
    pose_bones = armature_obj.pose.bones

    for bone_name, (origin_key, dest_key) in BONE_LANDMARK_MAP.items():
        if bone_name not in pose_bones:
            continue

        pose_bone = pose_bones[bone_name]

        origin = pts.get(origin_key)
        dest = pts.get(dest_key)

        if origin is None or dest is None:
            continue

        direction = dest - origin
        if direction.length < 1e-6:
            continue

        direction.normalize()

        # Rotar el hueso para apuntar hacia `direction`
        _orient_bone_to_direction(pose_bone, direction, smooth_factor)


def _orient_bone_to_direction(
    pose_bone: bpy.types.PoseBone,
    target_dir: Vector,
    smooth_factor: float,
):
    """
    Orienta el hueso para que apunte hacia `target_dir`.

    Usa cuaterniones y suaviza entre frames.
    """
    # Dirección actual del hueso (en su espacio de reposo)
    # Blender usa Y como eje longitudinal del hueso.
    rest_dir = Vector((0.0, 1.0, 0.0))

    # Calcular rotación necesaria en espacio local del padre
    # Simplificación: rotar para alinear rest_dir con target_dir
    try:
        q_target = rest_dir.rotation_difference(target_dir)
    except Exception:
        return

    # Suavizar con la rotación anterior
    bone_name = pose_bone.name
    if smooth_factor > 0.0 and bone_name in _last_quaternions:
        q_prev = _last_quaternions[bone_name]
        q_final = q_prev.slerp(q_target, 1.0 - smooth_factor)
    else:
        q_final = q_target

    _last_quaternions[bone_name] = q_final

    # Aplicar al pose bone
    pose_bone.rotation_mode = "QUATERNION"
    pose_bone.rotation_quaternion = q_final