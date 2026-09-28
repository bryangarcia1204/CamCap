"""
Exportador BVH con cinemática relativa y cuaterniones.

Corrige los problemas de:
  - Offsets mal calculados (ahora usa T-pose fija)
  - Rotaciones absolutas (ahora calcula rotaciones locales al padre)
  - Gimbal lock (usa cuaterniones internamente)

Fixes aplicados:
  - FIX 1: Raíz Hips normalizada al origen (primer frame como referencia)
  - FIX 2: Todos los frames incluidos (frames sin detección repiten la última pose)
  - FIX 3: Landmarks con vis baja usan la dirección de T-pose
  - FIX 4: Reset de estado en cada export

Referencias:
  - BVH format: pos_j = R_P(j) · offset_j + pos_P(j)
  - Para cada hueso se almacena: R_P(j)^-1 · R_j
"""
import os
import math
from typing import List, Dict, Optional, Tuple
from datetime import datetime

import numpy as np

from utils.logger import get_logger
from plugins.motion_capture_export.pose_tracker import (
    HybridPoseTracker, FrameResult, PersonDetection,
)

logger = get_logger("Plugin.BVHExporter")


# ============================================================
# ÍNDICES DE LANDMARKS MEDIAPIPE
# ============================================================

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


# ============================================================
# UTILIDADES DE CUATERNIONES
# ============================================================

def quat_from_two_vectors(v_from: np.ndarray, v_to: np.ndarray) -> np.ndarray:
    """
    Calcula el cuaternión que rota v_from a v_to.

    Retorna [x, y, z, w].
    """
    v_from = v_from / (np.linalg.norm(v_from) + 1e-9)
    v_to = v_to / (np.linalg.norm(v_to) + 1e-9)

    dot = np.dot(v_from, v_to)
    dot = max(-1.0, min(1.0, dot))

    if dot > 0.9999:
        return np.array([0.0, 0.0, 0.0, 1.0])

    if dot < -0.9999:
        # Vectores opuestos: rotar 180° alrededor de un eje perpendicular
        axis = np.cross(v_from, np.array([1.0, 0.0, 0.0]))
        if np.linalg.norm(axis) < 1e-6:
            axis = np.cross(v_from, np.array([0.0, 1.0, 0.0]))
        axis = axis / (np.linalg.norm(axis) + 1e-9)
        return np.array([axis[0], axis[1], axis[2], 0.0])

    axis = np.cross(v_from, v_to)
    w = 1.0 + dot
    q = np.array([axis[0], axis[1], axis[2], w])
    return q / (np.linalg.norm(q) + 1e-9)


def quat_conjugate(q: np.ndarray) -> np.ndarray:
    """Conjugado de un cuaternión [x, y, z, w]."""
    return np.array([-q[0], -q[1], -q[2], q[3]])


def quat_multiply(q1: np.ndarray, q2: np.ndarray) -> np.ndarray:
    """Multiplicación de cuaterniones [x, y, z, w]."""
    x1, y1, z1, w1 = q1
    x2, y2, z2, w2 = q2
    return np.array([
        w1*x2 + x1*w2 + y1*z2 - z1*y2,
        w1*y2 - x1*z2 + y1*w2 + z1*x2,
        w1*z2 + x1*y2 - y1*x2 + z1*w2,
        w1*w2 - x1*x2 - y1*y2 - z1*z2,
    ])


def quat_to_euler_zxy(q: np.ndarray) -> np.ndarray:
    """
    Convierte cuaternión [x, y, z, w] a Euler ZXY (grados).

    BVH estándar usa Zrotation, Xrotation, Yrotation en ese orden.
    """
    x, y, z, w = q

    # Matriz de rotación desde cuaternión
    R = np.array([
        [1 - 2*(y*y + z*z), 2*(x*y - z*w), 2*(x*z + y*w)],
        [2*(x*y + z*w), 1 - 2*(x*x + z*z), 2*(y*z - x*w)],
        [2*(x*z - y*w), 2*(y*z + x*w), 1 - 2*(x*x + y*y)],
    ])

    # Extraer Euler ZXY
    sy = -R[2, 0]
    sy = max(-1.0, min(1.0, sy))

    if abs(sy) < 0.9999:
        x_ang = math.asin(sy)
        y_ang = math.atan2(R[2, 1], R[2, 2])
        z_ang = math.atan2(R[1, 0], R[0, 0])
    else:
        # Gimbal lock
        x_ang = math.asin(sy)
        z_ang = 0.0
        y_ang = math.atan2(-R[0, 1], R[1, 1])

    return np.array([
        math.degrees(z_ang),
        math.degrees(x_ang),
        math.degrees(y_ang),
    ])


# ============================================================
# ESQUELETO DE REFERENCIA (T-POSE)
# ============================================================

# Offsets en T-pose (unidades arbitrarias, se escalan después).
# Y arriba, X derecha, Z adelante (convención BVH).
T_POSE_BONES = [
    # (nombre, padre, offset_x, offset_y, offset_z)
    ("Hips",       None,        0.0,   0.0,   0.0),
    ("Spine",      "Hips",      0.0,   0.15,  0.0),
    ("Chest",      "Spine",     0.0,   0.15,  0.0),
    ("Neck",       "Chest",     0.0,   0.12,  0.0),
    ("Head",       "Neck",      0.0,   0.15,  0.0),

    # Brazo izquierdo (T-pose: extendido hacia +X)
    ("LeftShoulder", "Chest",         0.08,  0.10,  0.0),
    ("LeftArm",      "LeftShoulder",  0.25,  0.0,   0.0),
    ("LeftForeArm",  "LeftArm",       0.25,  0.0,   0.0),
    ("LeftHand",     "LeftForeArm",   0.12,  0.0,   0.0),

    # Brazo derecho (T-pose: extendido hacia -X)
    ("RightShoulder", "Chest",         -0.08,  0.10,  0.0),
    ("RightArm",      "RightShoulder", -0.25,  0.0,   0.0),
    ("RightForeArm",  "RightArm",      -0.25,  0.0,   0.0),
    ("RightHand",     "RightForeArm",  -0.12,  0.0,   0.0),

    # Pierna izquierda (hacia abajo)
    ("LeftUpLeg",   "Hips",      0.10, -0.05,  0.0),
    ("LeftLeg",     "LeftUpLeg", 0.0,  -0.40,  0.0),
    ("LeftFoot",    "LeftLeg",   0.0,  -0.40,  0.0),
    ("LeftToeBase", "LeftFoot",  0.0,  -0.05,  0.15),

    # Pierna derecha
    ("RightUpLeg",   "Hips",       -0.10, -0.05,  0.0),
    ("RightLeg",     "RightUpLeg",  0.0,  -0.40,  0.0),
    ("RightFoot",    "RightLeg",    0.0,  -0.40,  0.0),
    ("RightToeBase", "RightFoot",   0.0,  -0.05,  0.15),
]


class Bone:
    """Un hueso del esqueleto BVH con jerarquía y canales."""

    def __init__(self, name: str, parent: Optional["Bone"] = None):
        self.name = name
        self.parent = parent
        self.children: List["Bone"] = []
        self.offset: Tuple[float, float, float] = (0.0, 0.0, 0.0)
        self.channels: List[str] = []
        self.is_root: bool = False

        if parent:
            parent.children.append(self)

    def __repr__(self):
        return f"<Bone {self.name} children={len(self.children)}>"


# ============================================================
# BVH EXPORTER
# ============================================================

class BVHExporter:
    """
    Exporta resultados a BVH con cinemática relativa.

    Uso:
        exporter = BVHExporter()
        exporter.export(results, output_path, fps=30.0)
    """

    def __init__(self):
        self.bones: Dict[str, Bone] = {}
        self.root: Optional[Bone] = None
        self.bone_order: List[str] = []

        # FIX 1: referencia para normalizar la raíz al origen
        self._first_root_position: Optional[np.ndarray] = None

        # FIX 3: última rotación conocida por hueso (para fallback)
        self._last_valid_rotations: Dict[str, np.ndarray] = {}

    # ==================== API PÚBLICA ====================

    def export(
        self,
        results: List[FrameResult],
        output_path: str,
        video_path: str = "",
        fps: float = 30.0,
    ) -> bool:
        """
        Exporta los resultados a BVH con cinemática relativa.

        Args:
            results: Lista de FrameResult del tracker (con TODOS los frames).
            output_path: Ruta del archivo .bvh.
            video_path: Ruta del video original (no usado).
            fps: FPS del video.

        Returns:
            True si se exportó correctamente.
        """
        try:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

            if not results:
                logger.error("❌ No hay frames para exportar")
                return False

            # FIX 4: reset del estado en cada export
            self._first_root_position = None
            self._last_valid_rotations = {}

            # 1. Construir esqueleto desde T-pose
            self._build_t_pose_skeleton()

            # 2. Contar frames con detección (para log)
            frames_with_detection = sum(
                1 for r in results
                if r.persons and r.persons[0].landmarks
                and len(r.persons[0].landmarks) == 33
            )

            logger.info(
                f"🎬 BVH: {frames_with_detection}/{len(results)} frames con detección"
            )

            # 3. Calcular datos por frame (FIX 2: incluye TODOS los frames)
            motion_frames = []
            last_valid_data: Optional[Dict] = None

            for frame in results:
                person = frame.persons[0] if frame.persons else None

                # FIX 3: filtrar landmarks con vis baja
                if person is not None and person.landmarks:
                    filtered = self._filter_landmarks(person.landmarks)
                else:
                    filtered = None

                if filtered is None or len(filtered) < 33:
                    # Frame sin detección válida → repetir la última pose conocida
                    if last_valid_data is not None:
                        motion_frames.append(self._copy_frame_data(last_valid_data))
                    else:
                        # Primer frame sin detección: usar pose neutral
                        motion_frames.append(self._make_neutral_frame())
                    continue

                # Calcular datos de este frame
                data = self._compute_frame_data(filtered)
                if data is None:
                    # Falla el cálculo → repetir la última pose
                    if last_valid_data is not None:
                        motion_frames.append(self._copy_frame_data(last_valid_data))
                    else:
                        motion_frames.append(self._make_neutral_frame())
                    continue

                last_valid_data = data
                motion_frames.append(data)

            if not motion_frames:
                logger.error("❌ No se pudieron calcular frames")
                return False

            # 4. Escribir BVH
            self._write_bvh(output_path, motion_frames, fps)

            size_kb = os.path.getsize(output_path) / 1024
            logger.info(
                f"✅ BVH exportado: {output_path} "
                f"({size_kb:.1f} KB, {len(motion_frames)} frames)"
            )
            return True

        except Exception as e:
            logger.error(f"❌ Error exportando BVH: {e}", exc_info=True)
            return False

    # ==================== ESQUELETO T-POSE ====================

    def _build_t_pose_skeleton(self):
        """Construye el esqueleto con offsets fijos de T-pose."""
        self.bones = {}
        self.root = None
        self.bone_order = []

        for name, parent_name, ox, oy, oz in T_POSE_BONES:
            parent = self.bones.get(parent_name) if parent_name else None
            bone = Bone(name, parent)
            bone.offset = (ox, oy, oz)

            if parent_name is None:
                bone.is_root = True
                bone.channels = ["Xposition", "Yposition", "Zposition",
                                 "Zrotation", "Xrotation", "Yrotation"]
                self.root = bone
            else:
                bone.channels = ["Zrotation", "Xrotation", "Yrotation"]

            self.bones[name] = bone
            self.bone_order.append(name)

        logger.debug(f"✅ Esqueleto T-pose: {len(self.bones)} huesos")

    # ==================== FILTRADO DE LANDMARKS (FIX 3) ====================

    def _filter_landmarks(self, landmarks: List[List[float]],
                          min_vis: float = 0.3) -> List[List[float]]:
        """
        FIX 3: Filtra landmarks con visibilidad muy baja.

        Los landmarks con vis < min_vis se marcan como (0,0,0,0) y
        luego el cálculo de direcciones usará la T-pose como fallback.
        """
        filtered = []
        for lm in landmarks:
            if len(lm) >= 4 and lm[3] < min_vis:
                filtered.append([0.0, 0.0, 0.0, 0.0])
            else:
                filtered.append([float(v) for v in lm])
        return filtered

    # ==================== CÁLCULO POR FRAME ====================

    def _compute_frame_data(self, landmarks: List[List[float]]) -> Optional[Dict]:
        """
        Calcula posiciones y rotaciones locales para un frame.

        Returns:
            Dict con 'root_position' y 'local_rotations' {bone_name: [Z, X, Y]}
            o None si falla.
        """
        try:
            # Posiciones 3D de los landmarks
            pts = self._landmarks_to_points(landmarks)

            # Direcciones globales de cada hueso
            global_dirs = self._compute_global_directions(pts)

            # Calcular rotaciones globales (cuaterniones)
            global_rotations: Dict[str, np.ndarray] = {}

            for name in self.bone_order:
                if name == "Hips":
                    global_rotations[name] = np.array([0.0, 0.0, 0.0, 1.0])
                    continue

                bone = self.bones[name]

                # Dirección global actual
                dir_global = global_dirs.get(name) if global_dirs else None

                # FIX 3: si no hay dirección válida, usar la dirección T-pose
                if dir_global is None:
                    dir_t_pose = np.array(bone.offset, dtype=np.float64)
                    norm = np.linalg.norm(dir_t_pose)
                    if norm < 1e-9:
                        global_rotations[name] = np.array([0.0, 0.0, 0.0, 1.0])
                        continue
                    dir_global = dir_t_pose / norm

                # Dirección global en T-pose (referencia)
                dir_t_pose = np.array(bone.offset, dtype=np.float64)
                norm_t = np.linalg.norm(dir_t_pose)
                if norm_t < 1e-9:
                    global_rotations[name] = np.array([0.0, 0.0, 0.0, 1.0])
                    continue
                dir_t_pose = dir_t_pose / norm_t

                # Rotación global (desde T-pose a actual)
                q_global = quat_from_two_vectors(dir_t_pose, dir_global)
                global_rotations[name] = q_global

            # Calcular rotaciones locales (relativas al padre)
            local_rotations: Dict[str, np.ndarray] = {}

            for name in self.bone_order:
                bone = self.bones[name]

                if name == "Hips":
                    local_rotations[name] = np.array([0.0, 0.0, 0.0])
                    continue

                q_global = global_rotations.get(
                    name, np.array([0.0, 0.0, 0.0, 1.0])
                )
                q_parent = global_rotations.get(
                    bone.parent.name if bone.parent else "",
                    np.array([0.0, 0.0, 0.0, 1.0]),
                )

                # R_local = R_parent^-1 * R_global
                q_local = quat_multiply(quat_conjugate(q_parent), q_global)

                # Convertir a Euler ZXY
                euler = quat_to_euler_zxy(q_local)

                # FIX 3: guardar como última rotación válida
                self._last_valid_rotations[name] = euler.copy()

                local_rotations[name] = euler

            # Posición de la raíz (hips) en el espacio del mundo
            hips_center = pts.get("hips_center", np.zeros(3))
            root_position = hips_center * 100.0  # escala a cm

            # FIX 1: normalizar al origen usando el primer frame como referencia
            if self._first_root_position is None:
                self._first_root_position = root_position.copy()
            root_position = root_position - self._first_root_position

            return {
                "root_position": root_position,
                "local_rotations": local_rotations,
            }

        except Exception as e:
            logger.debug(f"Error calculando frame: {e}", exc_info=True)
            return None

    def _copy_frame_data(self, data: Dict) -> Dict:
        """Copia profunda de un frame data (para reusar en frames sin detección)."""
        return {
            "root_position": data["root_position"].copy(),
            "local_rotations": {
                name: rot.copy()
                for name, rot in data["local_rotations"].items()
            },
        }

    def _make_neutral_frame(self) -> Dict:
        """Frame neutral (pose T-pose sin movimiento) para el primer frame sin detección."""
        return {
            "root_position": np.zeros(3),
            "local_rotations": {
                name: np.zeros(3) for name in self.bone_order
            },
        }

    # ==================== CONVERSIÓN DE LANDMARKS ====================

    def _landmarks_to_points(self, landmarks: List[List[float]]) -> Dict[str, np.ndarray]:
        """Convierte landmarks a puntos 3D con nombres."""

        def get(name: str) -> np.ndarray:
            idx = LM.get(name, -1)
            if idx < 0 or idx >= len(landmarks):
                return np.zeros(3)
            lm = landmarks[idx]
            return np.array([lm[0], lm[1], lm[2]], dtype=np.float64)

        left_hip = get("left_hip")
        right_hip = get("right_hip")
        left_shoulder = get("left_shoulder")
        right_shoulder = get("right_shoulder")
        nose = get("nose")

        hips_center = (left_hip + right_hip) * 0.5
        chest_center = (left_shoulder + right_shoulder) * 0.5
        spine_center = (hips_center + chest_center) * 0.5
        neck_center = chest_center + np.array([0.0, -0.05, 0.0])

        return {
            "hips_center": hips_center,
            "spine_center": spine_center,
            "chest_center": chest_center,
            "neck_center": neck_center,
            "head": nose,
            "left_shoulder": left_shoulder,
            "right_shoulder": right_shoulder,
            "left_hip": left_hip,
            "right_hip": right_hip,
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

    def _compute_global_directions(
        self, pts: Dict[str, np.ndarray]
    ) -> Optional[Dict[str, np.ndarray]]:
        """
        Calcula la dirección global de cada hueso desde los landmarks.

        FIX 3: si un landmark tiene (0,0,0) por vis baja, se ignora
        el hueso (no se añade a las direcciones).
        """
        dirs: Dict[str, np.ndarray] = {}

        mapping = {
            "Spine":         ("hips_center",     "spine_center"),
            "Chest":         ("spine_center",    "chest_center"),
            "Neck":          ("chest_center",    "neck_center"),
            "Head":          ("neck_center",     "head"),
            "LeftShoulder":  ("neck_center",     "left_shoulder"),
            "LeftArm":       ("left_shoulder",   "left_elbow"),
            "LeftForeArm":   ("left_elbow",      "left_wrist"),
            "LeftHand":      ("left_wrist",      "left_index"),
            "RightShoulder": ("neck_center",     "right_shoulder"),
            "RightArm":      ("right_shoulder",  "right_elbow"),
            "RightForeArm":  ("right_elbow",     "right_wrist"),
            "RightHand":     ("right_wrist",     "right_index"),
            "LeftUpLeg":     ("hips_center",     "left_hip"),
            "LeftLeg":       ("left_hip",        "left_knee"),
            "LeftFoot":      ("left_knee",       "left_ankle"),
            "LeftToeBase":   ("left_ankle",      "left_foot_index"),
            "RightUpLeg":    ("hips_center",     "right_hip"),
            "RightLeg":      ("right_hip",       "right_knee"),
            "RightFoot":     ("right_knee",      "right_ankle"),
            "RightToeBase":  ("right_ankle",     "right_foot_index"),
        }

        for bone_name, (origin_key, dest_key) in mapping.items():
            origin = pts.get(origin_key)
            dest = pts.get(dest_key)
            if origin is None or dest is None:
                continue

            # FIX 3: si alguno es (0,0,0) por vis baja, ignorar
            if np.linalg.norm(origin) < 1e-9 or np.linalg.norm(dest) < 1e-9:
                continue

            direction = dest - origin
            norm = np.linalg.norm(direction)
            if norm < 1e-6:
                continue

            dirs[bone_name] = direction / norm

        return dirs if dirs else None

    # ==================== ESCRITURA ====================

    def _write_bvh(self, output_path: str,
                   motion_frames: List[Dict],
                   fps: float):
        """Escribe el archivo BVH."""
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("HIERARCHY\n")
            self._write_hierarchy(f, self.root, indent=0)

            f.write("MOTION\n")
            f.write(f"Frames: {len(motion_frames)}\n")
            frame_time = 1.0 / fps if fps > 0 else 0.0333
            f.write(f"Frame Time: {frame_time:.6f}\n")

            for motion in motion_frames:
                values = []

                # Posición raíz
                root_pos = motion["root_position"]
                values.extend([root_pos[0], root_pos[1], root_pos[2]])

                # Rotaciones locales en orden
                rotations = motion["local_rotations"]
                for name in self.bone_order:
                    rot = rotations.get(name, np.zeros(3))
                    values.extend([rot[0], rot[1], rot[2]])

                f.write(" ".join(f"{v:.4f}" for v in values))
                f.write("\n")

    def _write_hierarchy(self, f, bone: Bone, indent: int = 0):
        """Escribe la jerarquía recursivamente."""
        ind = "  " * indent

        if bone.is_root:
            f.write(f"{ind}ROOT {bone.name}\n")
        else:
            f.write(f"{ind}JOINT {bone.name}\n")

        f.write(f"{ind}{{\n")
        f.write(
            f"{ind}  OFFSET {bone.offset[0]:.4f} "
            f"{bone.offset[1]:.4f} {bone.offset[2]:.4f}\n"
        )
        f.write(
            f"{ind}  CHANNELS {len(bone.channels)} "
            f"{' '.join(bone.channels)}\n"
        )

        for child in bone.children:
            self._write_hierarchy(f, child, indent + 1)

        if not bone.children:
            f.write(f"{ind}  End Site\n")
            f.write(f"{ind}  {{\n")
            f.write(f"{ind}    OFFSET 0.0 0.0 0.0\n")
            f.write(f"{ind}  }}\n")

        f.write(f"{ind}}}\n")