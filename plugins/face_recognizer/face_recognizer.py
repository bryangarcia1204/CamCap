"""
Reconocimiento facial - v3
Modelos soportados:
  - sface (OpenCV SFace + YuNet) — recomendado, rápido en CPU
  - dlib (face_recognition) — preciso pero lento en CPU
  - mediapipe (Google) — rápido pero requiere instalación

Todos los parámetros son ajustables desde la UI (advanced_config).

FIX v3:
- Fix del nombre base (agrupa Brayan_1.jpg, Brayan_2.jpg como "Brayan")
- Logs DEBUG de diagnóstico en todos los puntos críticos
- Guardado de caras alineadas en debug_faces/ para inspección
- Verificación de embeddings (norma, shape, valores)
- Log de TODOS los matches, no solo el mejor

FIX v4 (migración a plugin):
- _find_models_dir() con fallback a detection/models/
"""
import os
import time
import numpy as np
import cv2
from typing import Optional, List, Tuple
from utils.logger import get_logger
from utils.config_loader import advanced_config

logger = get_logger("FaceRecognizer")


def _find_models_dir() -> str:
    """
    Localiza el directorio de modelos.
    
    Prioridad:
    1. plugins/face_recognizer/models/
    2. detection/models/ (fallback para compatibilidad)
    3. Crear plugins/face_recognizer/models/
    """
    here = os.path.dirname(os.path.abspath(__file__))
    plugin_models = os.path.join(here, "models")

    if os.path.isdir(plugin_models):
        return plugin_models

    # Fallback: detection/models/
    fallback = os.path.join(
        os.path.dirname(os.path.dirname(here)),
        "detection", "models"
    )
    if os.path.isdir(fallback):
        logger.debug(f"🧠 [models] Usando fallback: {fallback}")
        return fallback

    # Último recurso
    os.makedirs(plugin_models, exist_ok=True)
    return plugin_models


class FaceRecognizer:
    """
    Reconocimiento facial con soporte para múltiples backends.

    Backends:
        - "sface": OpenCV SFace + YuNet (recomendado)
        - "dlib": face_recognition library
        - "mediapipe": Google MediaPipe (futuro)
    """

    def __init__(self, known_faces_dir="known_faces", tolerance=None, model=None):
        cfg = advanced_config.get_all()

        self.known_faces_dir = known_faces_dir
        self.tolerance = tolerance if tolerance is not None else 0.6
        self.model = model if model is not None else cfg.get("face_detector_model", "sface")
        self.min_face_size = cfg.get("face_min_face_size", 20)
        self.recognition_scale = cfg.get("face_recognition_scale", 0.25)
        self.score_threshold = cfg.get("face_detector_score_threshold", 0.9)

        # Nuevos
        self.nms_threshold = cfg.get("face_nms_threshold", 0.3)
        self.top_k = cfg.get("face_top_k", 5000)
        self.sface_threshold = cfg.get("face_sface_threshold", 0.363)
        self.input_size = cfg.get("face_input_size", 320)

        # Estado
        self.known_embeddings: List[np.ndarray] = []
        self.known_names: List[str] = []
        self.face_locations = []
        self.face_names = []
        self._available = False

        # Backends
        self._detector = None
        self._recognizer = None
        self._dlib = None

        # Directorio de debug
        self._debug_dir = "debug_faces"

        logger.debug(
            f"🔧 [init] FaceRecognizer: model={self.model}, "
            f"tolerance={self.tolerance}, min_face_size={self.min_face_size}, "
            f"input_size={self.input_size}, sface_threshold={self.sface_threshold}, "
            f"score_threshold={self.score_threshold}, "
            f"known_faces_dir={self.known_faces_dir}"
        )

        # Cargar modelo
        self._load_model()

        if self._available:
            self.load_known_faces()

        logger.info(
            f"FaceRecognizer: model={self.model}, "
            f"tolerance={self.tolerance}, "
            f"available={self._available}"
        )

    def _load_model(self):
        """Carga el modelo según config"""
        if self.model == "sface":
            self._load_sface()
        elif self.model == "dlib":
            self._load_dlib()
        elif self.model == "mediapipe":
            self._load_mediapipe()
        else:
            logger.warning(f"Modelo desconocido: {self.model}, usando sface")
            self.model = "sface"
            self._load_sface()

    # ==================== SFACE ====================

    def _load_sface(self):
        """Carga YuNet + SFace"""
        try:
            model_dir = _find_models_dir()

            yunet_path = os.path.join(model_dir, "face_detection_yunet_2023mar.onnx")
            sface_path = os.path.join(model_dir, "face_recognition_sface_2021dec.onnx")

            logger.debug(
                f"🧠 [face] Cargando SFace:\n"
                f"     yunet={yunet_path} exists={os.path.exists(yunet_path)}\n"
                f"     sface={sface_path} exists={os.path.exists(sface_path)}"
            )

            if not os.path.exists(yunet_path) or not os.path.exists(sface_path):
                logger.warning(
                    "⚠️ Modelos YuNet/SFace no encontrados en 'plugins/face_recognizer/models/'.\n"
                    "   Descárgalos de: https://github.com/opencv/opencv_zoo/tree/main/models\n"
                    "   - face_detection_yunet → face_detection_yunet_2023mar.onnx\n"
                    "   - face_recognition_sface → face_recognition_sface_2021dec.onnx"
                )
                self._available = False
                return

            self._detector = cv2.FaceDetectorYN.create(
                model=yunet_path,
                config="",
                input_size=(self.input_size, self.input_size),
                score_threshold=self.score_threshold,
                nms_threshold=self.nms_threshold,
                top_k=self.top_k
            )
            self._recognizer = cv2.FaceRecognizerSF.create(
                model=sface_path,
                config=""
            )
            self._available = True

            logger.debug(
                f"✅ [face] SFace + YuNet cargados: "
                f"input={self.input_size}, score_threshold={self.score_threshold}, "
                f"nms={self.nms_threshold}, top_k={self.top_k}, "
                f"sface_threshold={self.sface_threshold}"
            )
            logger.info("✅ SFace + YuNet cargados")
        except Exception as e:
            logger.error(f"❌ Error cargando SFace/YuNet: {e}")
            self._available = False

    def _detect_faces_sface(self, frame: np.ndarray) -> np.ndarray:
        """Detecta caras con YuNet"""
        if self._detector is None:
            return np.array([])
        h, w = frame.shape[:2]
        self._detector.setInputSize((w, h))
        _, faces = self._detector.detect(frame)
        if faces is None:
            return np.array([])
        return faces

    def _recognize_sface(self, frame: np.ndarray) -> Tuple[list, list]:
        """Reconoce caras con SFace"""
        faces = self._detect_faces_sface(frame)
        if len(faces) == 0:
            return [], []

        logger.debug(f"🧠 [face] YuNet detectó {len(faces)} caras")

        locations = []
        names = []

        for face in faces:
            x, y, w, h = face[:4]

            if w < self.min_face_size or h < self.min_face_size:
                logger.debug(
                    f"🧠 [face] Cara filtrada por tamaño: {w:.0f}x{h:.0f} "
                    f"(min={self.min_face_size})"
                )
                continue

            locations.append((int(y), int(x + w), int(y + h), int(x)))

            try:
                face_align = self._recognizer.alignCrop(frame, face)
                embedding = self._recognizer.feature(face_align)

                logger.debug(
                    f"🧠 [face-live] Embedding generado: "
                    f"shape={embedding.shape}, norm={np.linalg.norm(embedding):.3f}, "
                    f"score_yunet={face[-1]:.3f}"
                )
            except Exception as e:
                logger.debug(f"🧠 [face] Error extrayendo embedding: {e}")
                names.append("Desconocido")
                continue

            if self.known_embeddings:
                best_score = 0.0
                best_name = "Desconocido"

                for known_emb, name in zip(self.known_embeddings, self.known_names):
                    try:
                        score = self._recognizer.match(
                            embedding, known_emb,
                            cv2.FaceRecognizerSF_FR_COSINE
                        )

                        logger.debug(
                            f"🧠 [face-match] vs '{name}': "
                            f"score={score:.4f} "
                            f"(threshold={self.sface_threshold})"
                        )

                        if score > best_score:
                            best_score = score
                            best_name = name
                    except Exception as e:
                        logger.debug(f"🧠 [face-match] Error comparando con {name}: {e}")
                        continue

                if best_score >= self.sface_threshold:
                    names.append(best_name)
                    logger.debug(
                        f"✅ [face-match] MATCH: name={best_name}, "
                        f"score={best_score:.4f} >= {self.sface_threshold}"
                    )
                else:
                    names.append("Desconocido")
                    logger.debug(
                        f"❌ [face-match] SIN MATCH: mejor={best_name}, "
                        f"score={best_score:.4f} < {self.sface_threshold}"
                    )
            else:
                logger.debug(
                    "⚠️ [face] No hay embeddings conocidos — "
                    "todas las caras serán 'Desconocido'"
                )
                names.append("Desconocido")

        return locations, names

    # ==================== DLIB ====================

    def _load_dlib(self):
        """Carga face_recognition (dlib)"""
        try:
            import face_recognition
            self._dlib = face_recognition
            self._available = True
            logger.info("✅ face_recognition (dlib) cargado")
        except ImportError:
            logger.warning("⚠️ face_recognition no instalado. pip install face_recognition")
            self._available = False

    def _recognize_dlib(self, frame: np.ndarray) -> Tuple[list, list]:
        """Reconoce caras con dlib"""
        if not self._dlib:
            return [], []

        small_frame = cv2.resize(
            frame, (0, 0),
            fx=self.recognition_scale,
            fy=self.recognition_scale
        )
        rgb_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

        face_locations = self._dlib.face_locations(rgb_small, model="hog")
        face_encodings = self._dlib.face_encodings(rgb_small, face_locations)

        logger.debug(f"🧠 [face] dlib detectó {len(face_locations)} caras")

        names = []
        for encoding in face_encodings:
            if self.known_embeddings:
                matches = self._dlib.compare_faces(
                    self.known_embeddings, encoding, tolerance=self.tolerance
                )
                name = "Desconocido"
                if True in matches:
                    distances = self._dlib.face_distance(self.known_embeddings, encoding)
                    best_idx = np.argmin(distances)
                    if matches[best_idx]:
                        name = self.known_names[best_idx]
                        logger.debug(
                            f"🧠 [face] dlib match: name={name}, "
                            f"distance={distances[best_idx]:.3f}"
                        )
                names.append(name)
            else:
                names.append("Desconocido")

        scale = int(1 / self.recognition_scale)
        locations = [
            (top * scale, right * scale, bottom * scale, left * scale)
            for (top, right, bottom, left) in face_locations
        ]

        return locations, names

    def _load_mediapipe(self):
        """Placeholder para MediaPipe"""
        try:
            import mediapipe as mp
            self._mp = mp
            self._mp_face = mp.solutions.face_detection.FaceDetection(
                model_selection=0, min_detection_confidence=self.score_threshold
            )
            self._available = True
            logger.info("✅ MediaPipe cargado")
        except ImportError:
            logger.warning("⚠️ mediapipe no instalado. pip install mediapipe")
            self._available = False

    def _recognize_mediapipe(self, frame: np.ndarray) -> Tuple[list, list]:
        """Reconoce caras con MediaPipe (solo detección por ahora)"""
        if not hasattr(self, '_mp_face'):
            return [], []

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self._mp_face.process(rgb)

        locations = []
        names = []

        if results.detections:
            logger.debug(f"🧠 [face] MediaPipe detectó {len(results.detections)} caras")

            h, w = frame.shape[:2]
            for detection in results.detections:
                bbox = detection.location_data.relative_bounding_box
                x = int(bbox.xmin * w)
                y = int(bbox.ymin * h)
                bw = int(bbox.width * w)
                bh = int(bbox.height * h)

                if bw < self.min_face_size or bh < self.min_face_size:
                    continue

                locations.append((y, x + bw, y + bh, x))
                names.append("Desconocido")

        return locations, names

    # ==================== API PÚBLICA ====================

    def recognize(self, frame: np.ndarray) -> Tuple[list, list]:
        """Punto de entrada - delega al backend configurado"""
        if not self._available:
            return [], []

        if self.model == "sface":
            locations, names = self._recognize_sface(frame)
        elif self.model == "dlib":
            locations, names = self._recognize_dlib(frame)
        elif self.model == "mediapipe":
            locations, names = self._recognize_mediapipe(frame)
        else:
            return [], []

        self.face_locations = locations
        self.face_names = names
        return locations, names

    @staticmethod
    def _extract_base_name(filename_no_ext: str) -> str:
        """
        Extrae el nombre base de un archivo.

        Ejemplos:
            "Brayan"      → "Brayan"
            "Brayan_1"    → "Brayan"
            "Brayan_2"    → "Brayan"
            "Brayan_abc"  → "Brayan_abc" (no es numérico, se mantiene)
            "Juan_Perez_1"→ "Juan_Perez"

        Esto permite agrupar múltiples fotos de la misma persona.
        """
        if "_" in filename_no_ext:
            parts = filename_no_ext.rsplit("_", 1)
            if parts[-1].isdigit():
                return parts[0]
        return filename_no_ext

    def load_known_faces(self) -> int:
        """Carga las caras conocidas"""
        if not self._available:
            logger.debug("🧠 [load] Reconocedor no disponible")
            return 0

        self.known_embeddings.clear()
        self.known_names.clear()

        if not os.path.exists(self.known_faces_dir):
            os.makedirs(self.known_faces_dir, exist_ok=True)
            logger.debug(f"🧠 [face] known_faces_dir creado: {self.known_faces_dir}")
            return 0

        try:
            files = os.listdir(self.known_faces_dir)
        except Exception as e:
            logger.error(f"🧠 [load] Error listando {self.known_faces_dir}: {e}")
            return 0

        valid_extensions = ('.jpg', '.jpeg', '.png', '.bmp')
        image_files = [f for f in files if f.lower().endswith(valid_extensions)]

        logger.debug(
            f"🧠 [load] Procesando {len(image_files)} imágenes "
            f"de {self.known_faces_dir}"
        )

        count = 0
        failed = []
        no_face = []
        low_score = []

        for filename in image_files:
            file_path = os.path.join(self.known_faces_dir, filename)
            base_name = os.path.splitext(filename)[0]
            group_name = self._extract_base_name(base_name)

            try:
                img = cv2.imread(file_path)
                if img is None:
                    failed.append((filename, "cv2.imread devolvió None"))
                    logger.debug(f"🧠 [load] {filename}: no se pudo leer")
                    continue

                logger.debug(
                    f"🧠 [load] {filename}: "
                    f"shape={img.shape}, dtype={img.dtype}, "
                    f"group_name='{group_name}'"
                )

                if self.model == "sface":
                    faces = self._detect_faces_sface(img)

                    logger.debug(
                        f"🧠 [load] {filename}: YuNet detectó {len(faces)} caras"
                    )

                    if len(faces) == 0:
                        no_face.append(filename)
                        continue

                    face = max(faces, key=lambda f: f[2] * f[3])

                    logger.debug(
                        f"🧠 [load] {filename}: cara elegida → "
                        f"x={face[0]:.0f}, y={face[1]:.0f}, "
                        f"w={face[2]:.0f}, h={face[3]:.0f}, "
                        f"score={face[-1]:.3f}"
                    )

                    if face[2] < self.min_face_size or face[3] < self.min_face_size:
                        low_score.append(
                            (filename, f"cara pequeña {face[2]:.0f}x{face[3]:.0f}")
                        )

                    face_align = self._recognizer.alignCrop(img, face)
                    embedding = self._recognizer.feature(face_align)

                elif self.model == "dlib":
                    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    encodings = self._dlib.face_encodings(rgb)
                    if not encodings:
                        no_face.append(filename)
                        continue
                    embedding = encodings[0]
                    face_align = None
                else:
                    continue

                emb_norm = float(np.linalg.norm(embedding))
                if emb_norm < 0.1:
                    failed.append(
                        (filename, f"embedding norm muy bajo: {emb_norm:.3f}")
                    )
                    logger.warning(
                        f"⚠️ [load] {filename}: embedding norm={emb_norm:.3f} "
                        f"(demasiado bajo, se ignora)"
                    )
                    continue

                logger.debug(
                    f"🧠 [load] {filename}: embedding OK → "
                    f"shape={embedding.shape}, norm={emb_norm:.3f}, "
                    f"first5={embedding.flatten()[:5]}"
                )

                self.known_embeddings.append(embedding)
                self.known_names.append(group_name)
                count += 1

                logger.info(
                    f"  ✅ Cargado: {group_name} (desde {filename})"
                )

                if face_align is not None:
                    try:
                        os.makedirs(self._debug_dir, exist_ok=True)
                        debug_path = os.path.join(
                            self._debug_dir,
                            f"aligned_{group_name}_{base_name}.jpg"
                        )
                        cv2.imwrite(debug_path, face_align)
                        logger.debug(
                            f"🧠 [load] Cara alineada guardada: {debug_path}"
                        )
                    except Exception as e:
                        logger.debug(f"🧠 [load] No se pudo guardar debug: {e}")

            except Exception as e:
                failed.append((filename, f"{type(e).__name__}: {e}"))
                logger.error(f"❌ Error cargando {filename}: {e}", exc_info=True)

        logger.debug(
            f"🧠 [load] RESUMEN:\n"
            f"     ✅ Cargadas: {count}\n"
            f"     ⚠️ Sin cara: {len(no_face)} {no_face[:5]}\n"
            f"     ⚠️ Cara pequeña: {len(low_score)} {low_score[:5]}\n"
            f"     ❌ Fallidas: {len(failed)} {failed[:5]}\n"
            f"     📁 Debug guardado en: {self._debug_dir}/"
        )

        if count > 0:
            unique_names = set(self.known_names)
            if len(unique_names) < count:
                logger.debug(
                    f"🧠 [load] Agrupados {count} embeddings en "
                    f"{len(unique_names)} persona(s): {unique_names}"
                )

        logger.info(f"✅ {count} caras conocidas cargadas")

        if count == 0 and len(image_files) > 0:
            logger.warning(
                f"⚠️ Se encontraron {len(image_files)} archivos pero NINGUNA "
                f"cara fue reconocida. Revisa los logs [load] para diagnóstico."
            )

        return count

    def draw_faces(self, frame: np.ndarray) -> np.ndarray:
        """Dibuja rectángulos y nombres en el frame"""
        result = frame.copy()
        for (top, right, bottom, left), name in zip(self.face_locations, self.face_names):
            if name == "Desconocido":
                color = (0, 0, 255)
                label = "❓ Desconocido"
            else:
                color = (0, 255, 0)
                label = f"✅ {name}"

            cv2.rectangle(result, (left, top), (right, bottom), color, 2)
            cv2.rectangle(result, (left, bottom - 30), (right, bottom), color, cv2.FILLED)
            cv2.putText(result, label, (left + 6, bottom - 8),
                        cv2.FONT_HERSHEY_DUPLEX, 0.6, (255, 255, 255), 1)
        return result

    def get_unknown_count(self) -> int:
        return self.face_names.count("Desconocido")

    def get_known_count(self) -> int:
        return len(self.face_names) - self.get_unknown_count()

    def add_known_face(self, image_path: str, person_name: str) -> bool:
        """Añade una cara conocida copiando la imagen al directorio"""
        if not self._available:
            return False
        try:
            import shutil
            dest = os.path.join(self.known_faces_dir, f"{person_name}.jpg")
            shutil.copy2(image_path, dest)
            self.load_known_faces()
            logger.debug(f"🧠 [face] Cara añadida: {person_name} desde {image_path}")
            return True
        except Exception as e:
            logger.error(f"Error añadiendo cara: {e}")
            return False

    def is_available(self) -> bool:
        return self._available

    def reload_config(self):
        """Recarga config y modelo si cambió"""
        from utils.config_loader import advanced_config
        cfg = advanced_config.get_all()

        old_model = self.model
        old_input_size = self.input_size
        old_threshold = self.sface_threshold
        old_score_threshold = self.score_threshold

        self.min_face_size = cfg.get("face_min_face_size", 20)
        self.recognition_scale = cfg.get("face_recognition_scale", 0.25)
        self.score_threshold = cfg.get("face_detector_score_threshold", 0.9)
        self.nms_threshold = cfg.get("face_nms_threshold", 0.3)
        self.top_k = cfg.get("face_top_k", 5000)
        self.sface_threshold = cfg.get("face_sface_threshold", 0.363)
        self.input_size = cfg.get("face_input_size", 320)

        new_model = cfg.get("face_detector_model", "sface")

        if new_model != self.model:
            logger.info(f"🔄 Cambiando modelo facial: {self.model} → {new_model}")
            logger.debug(f"🧠 [reload] Modelo cambia: {self.model}→{new_model}")
            self.model = new_model
            self._load_model()
            if self._available:
                self.load_known_faces()
        else:
            if self.model == "sface" and self._available:
                logger.debug(
                    f"🧠 [reload] Recargando SFace: "
                    f"input={old_input_size}→{self.input_size}, "
                    f"sface_threshold={old_threshold}→{self.sface_threshold}, "
                    f"score_threshold={old_score_threshold}→{self.score_threshold}"
                )
                self._load_sface()
                self.load_known_faces()

        logger.info(f"🔄 FaceRecognizer recargado: model={self.model}")
        return True

    def reload_known_faces(self):
        """Fuerza recarga de caras conocidas sin tocar el modelo."""
        logger.debug("🧠 [reload] Recargando solo caras conocidas...")
        return self.load_known_faces()