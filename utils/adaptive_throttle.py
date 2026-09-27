"""
Sistema de throttling adaptativo basado en CPU/GPU real.

- Mide CPU del proceso (no del sistema)
- Mide GPU si está disponible
- Mide tiempo de procesamiento por frame
- Ajusta el skip dinámicamente para mantener un objetivo de uso de recursos
"""
import time
import threading
from typing import Optional, Dict
from collections import deque

from utils.logger import get_logger

logger = get_logger("AdaptiveThrottle")


class AdaptiveThrottle:
    """
    Controla dinámicamente cuántos frames saltar según la carga de CPU/GPU.

    Objetivo: mantener el uso de CPU/GPU por debajo de un umbral,
    saltando frames cuando es necesario.
    """

    def __init__(self,
                 target_cpu: float = 0.70,
                 target_gpu: float = 0.80,
                 max_skip: int = 3,
                 check_interval: float = 1.0,
                 process_id: Optional[int] = None):
        """
        Args:
            target_cpu: uso objetivo de CPU del proceso (0-1)
            target_gpu: uso objetivo de GPU (0-1)
            max_skip: máximo de frames a saltar (0=ninguno, 3=salta 3 de cada 4)
            check_interval: intervalo entre comprobaciones (segundos)
            process_id: PID del proceso (None = proceso actual)
        """
        self.target_cpu = target_cpu
        self.target_gpu = target_gpu
        self.max_skip = max(1, max_skip)
        self.check_interval = check_interval
        self.process_id = process_id

        self.hysteresis = 0.30              # ← NUEVO
        self.gpu_measure_sample = 5

        # Estado actual
        self._current_skip = 0
        self._last_check = 0.0

        # Métricas
        self._cpu_percent = 0.0
        self._gpu_percent = 0.0
        self._frame_times = deque(maxlen=30)  # tiempos de los últimos frames
        self._lock = threading.Lock()

        # Para medir CPU del proceso
        self._process = None
        self._init_process()

        # Para medir GPU
        self._gpu_available = False
        self._init_gpu()

        logger.info(
            f"AdaptiveThrottle: target_cpu={target_cpu:.0%}, "
            f"target_gpu={target_gpu:.0%}, max_skip={max_skip}"
        )

    def _init_process(self):
        try:
            import psutil
            if self.process_id:
                self._process = psutil.Process(self.process_id)
            else:
                self._process = psutil.Process()
            # Primera llamada para inicializar
            self._process.cpu_percent(interval=None)
        except Exception as e:
            logger.warning(f"No se pudo inicializar psutil.Process: {e}")
            self._process = None

    def _init_gpu(self):
        """Inicializa el monitor de GPU si está disponible"""
        try:
            import pynvml
            pynvml.nvmlInit()
            self._nvml_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            self._nvml = pynvml
            self._gpu_available = True
            logger.info("GPU detectada para throttling adaptativo")
        except Exception:
            try:
                import GPUtil
                gpus = GPUtil.getGPUs()
                if gpus:
                    self._gputil = GPUtil
                    self._gpu_available = True
                    logger.info("GPU (GPUtil) detectada para throttling")
            except Exception:
                self._gpu_available = False

    def get_current_skip(self) -> int:
        """Retorna cuántos frames saltar actualmente (0-N)"""
        with self._lock:
            return self._current_skip

    def should_process_frame(self, frame_counter: int) -> bool:
        """
        Decide si procesar un frame.

        Args:
            frame_counter: contador incremental de frames recibidos

        Returns:
            True si hay que procesar el frame, False si hay que saltarlo
        """
        with self._lock:
            skip = self._current_skip

        if skip == 0:
            return True

        # Procesar 1 de cada (skip + 1) frames
        return frame_counter % (skip + 1) == 0

    def record_frame_time(self, elapsed: float):
        """Registra el tiempo de procesamiento de un frame"""
        with self._lock:
            self._frame_times.append(elapsed)

    def check_and_adjust(self):
        """
        Comprueba CPU/GPU y ajusta el skip.
        Llamar periódicamente (cada check_interval segundos).
        """
        now = time.time()
        if now - self._last_check < self.check_interval:
            return

        self._last_check = now

        # Medir CPU del proceso
        if self._process:
            try:
                self._cpu_percent = self._process.cpu_percent(interval=None) / 100.0
            except Exception:
                self._cpu_percent = 0.0

        # Medir GPU
        if self._gpu_available:
            self._gpu_percent = self._measure_gpu()
        else:
            self._gpu_percent = 0.0

        # Ajustar skip
        self._adjust_skip()

    def _measure_gpu(self) -> float:
        """Mide el uso de GPU (0-1)"""
        try:
            if hasattr(self, '_nvml'):
                util = self._nvml.nvmlDeviceGetUtilizationRates(self._nvml_handle)
                return util.gpu / 100.0
            elif hasattr(self, '_gputil'):
                gpus = self._gputil.getGPUs()
                if gpus:
                    return gpus[0].load
        except Exception:
            pass
        return 0.0

    def _adjust_skip(self):
        """Ajusta el skip según las métricas actuales"""
        with self._lock:
            current = self._current_skip
            cpu = self._cpu_percent
            gpu = self._gpu_percent

        # Determinar si subir o bajar el skip
        cpu_overload = cpu > self.target_cpu
        gpu_overload = self._gpu_available and gpu > self.target_gpu

        # Margen de histéresis para evitar fluctuaciones

        cpu_underload = cpu < (self.target_cpu - self.hysteresis)  # ← antes 0.30
        gpu_underload = (not self._gpu_available) or gpu < (self.target_gpu - self.hysteresis)

        new_skip = current

        if cpu_overload or gpu_overload:
            # Subir skip gradualmente
            new_skip = min(self.max_skip, current + 1)
            if new_skip != current:
                logger.info(
                    f"⚡ Skip aumentado: {current} → {new_skip} "
                    f"(CPU: {cpu:.0%}, GPU: {gpu:.0%})"
                )
        elif cpu_underload and gpu_underload and current > 0:
            # Bajar skip gradualmente (solo si estamos holgados)
            # Añadimos un margen para no oscilar
            if current > 0:
                new_skip = max(0, current - 1)
                if new_skip != current:
                    logger.info(
                        f"⚡ Skip reducido: {current} → {new_skip} "
                        f"(CPU: {cpu:.0%}, GPU: {gpu:.0%})"
                    )

        with self._lock:
            self._current_skip = new_skip

    def get_metrics(self) -> Dict:
        """Retorna las métricas actuales"""
        with self._lock:
            frame_times = list(self._frame_times)
            avg_frame_time = sum(frame_times) / len(frame_times) if frame_times else 0

        return {
            "cpu_percent": self._cpu_percent,
            "gpu_percent": self._gpu_percent,
            "gpu_available": self._gpu_available,
            "current_skip": self._current_skip,
            "max_skip": self.max_skip,
            "avg_frame_time_ms": avg_frame_time * 1000,
        }

    def reset(self):
        """Reinicia el throttling"""
        with self._lock:
            self._current_skip = 0
            self._frame_times.clear()
        logger.debug("AdaptiveThrottle reiniciado")