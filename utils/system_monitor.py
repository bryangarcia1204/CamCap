"""
Monitor de recursos del sistema: CPU, RAM y GPU
Soporta:
  - CPU/RAM: psutil (obligatorio)
  - GPU NVIDIA: pynvml (opcional, recomendado)
  - GPU NVIDIA: GPUtil (opcional, fallback)
  - GPU AMD: pyadl (opcional)
"""
import threading
import time
from typing import Optional, List, Dict
from utils.config_loader import advanced_config

from utils.logger import get_logger

logger = get_logger("SystemMonitor")


class SystemMonitor:
    """Monitor de recursos del sistema (Singleton)"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        # Callbacks registrados
        self._callbacks = []
        self._lock = threading.Lock()

        # Últimos valores
        self._cpu_percent = 0.0
        self._ram_percent = 0.0
        self._ram_used_gb = 0.0
        self._ram_total_gb = 0.0
        self._gpu_percent = 0.0
        self._gpu_mem_percent = 0.0
        self._gpu_name = ""
        self._gpu_temp = 0.0

        # Estado
        self._running = False
        self._thread = None
        self._poll_interval = advanced_config.get("system_monitor_interval", 1.0)

        # Backends
        self._psutil = None
        self._pynvml = None
        self._gputil = None
        self._adl = None
        self._gpu_backend = None
        self._gpu_handle = None

        self._detect_backends()

        logger.info(f"📊 SystemMonitor inicializado (GPU: {self._gpu_backend or 'no detectada'})")

    def _detect_backends(self):
        """Detecta qué librerías están disponibles"""
        # psutil (obligatorio para CPU/RAM)
        try:
            import psutil
            self._psutil = psutil
            logger.info("✅ psutil disponible para CPU/RAM")
        except ImportError:
            logger.warning("⚠️ psutil no instalado. Instala con: pip install psutil")
            self._psutil = None

        from utils.config_loader import advanced_config
        gpu_index = advanced_config.get("system_monitor_gpu_index", 0)

        # NVIDIA NVML
        try:
            import pynvml
            pynvml.nvmlInit()
            count = pynvml.nvmlDeviceGetCount()
            if count > gpu_index:
                self._gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(gpu_index)
                name = pynvml.nvmlDeviceGetName(self._gpu_handle)
                if isinstance(name, bytes):
                    name = name.decode('utf-8')
                self._gpu_name = name
                self._gpu_backend = "nvml"
                self._pynvml = pynvml
                logger.info(f"✅ GPU NVIDIA detectada: {name}")
                return
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"NVML init failed: {e}")

        # GPUtil (fallback NVIDIA)
        try:
            import GPUtil
            gpus = GPUtil.getGPUs()
            if gpus:
                self._gpu_name = gpus[0].name
                self._gpu_backend = "gputil"
                self._gputil = GPUtil
                logger.info(f"✅ GPU (GPUtil) detectada: {self._gpu_name}")
                return
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"GPUtil failed: {e}")

        # AMD ADL
        try:
            import pyadl
            adl = pyadl.ADLManager.getInstance()
            devices = adl.getDevices()
            if devices:
                self._gpu_name = devices[0].name
                self._gpu_backend = "adl"
                self._adl = adl
                logger.info(f"✅ GPU AMD detectada: {self._gpu_name}")
                return
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"ADL failed: {e}")

        logger.info("ℹ️ No se detectó GPU monitoreable")

    # ==================== CALLBACKS ====================

    def register_callback(self, callback):
        """Registra un callback que recibe un dict con las métricas"""
        with self._lock:
            if callback not in self._callbacks:
                self._callbacks.append(callback)

    def unregister_callback(self, callback):
        with self._lock:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

    def _notify_callbacks(self):
        """Notifica a todos los callbacks con las métricas actuales"""
        metrics = self.get_metrics()
        with self._lock:
            callbacks = list(self._callbacks)

        for cb in callbacks:
            try:
                cb(metrics)
            except Exception as e:
                logger.debug(f"Error en callback de monitor: {e}")

    # ==================== START / STOP ====================

    def start(self):
        """Inicia el monitoreo en background"""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="SystemMonitor")
        self._thread.start()
        logger.info("📊 SystemMonitor iniciado")

    def _run(self):
        """Bucle principal de monitoreo"""
        # Primera lectura de CPU para inicializar psutil
        if self._psutil:
            try:
                self._psutil.cpu_percent(interval=None)
            except Exception:
                pass

        while self._running:
            try:
                self._update_metrics()
                self._notify_callbacks()
            except Exception as e:
                logger.error(f"Error en SystemMonitor: {e}")

            # Esperar (dividido en pasos para salir rápido)
            elapsed = 0.0
            step = 0.1
            while self._running and elapsed < self._poll_interval:
                time.sleep(step)
                elapsed += step

    def stop(self):
        """Detiene el monitoreo"""
        if not self._running:
            return
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("📊 SystemMonitor detenido")

    # ==================== MÉTRICAS ====================

    def _update_metrics(self):
        """Actualiza todos los valores"""
        if self._psutil:
            try:
                self._cpu_percent = self._psutil.cpu_percent(interval=None)
            except Exception:
                self._cpu_percent = 0.0

            try:
                mem = self._psutil.virtual_memory()
                self._ram_percent = mem.percent
                self._ram_used_gb = mem.used / (1024 ** 3)
                self._ram_total_gb = mem.total / (1024 ** 3)
            except Exception:
                pass

        self._update_gpu()

    def _update_gpu(self):
        """Actualiza las métricas de GPU según el backend"""
        if self._gpu_backend == "nvml":
            try:
                util = self._pynvml.nvmlDeviceGetUtilizationRates(self._gpu_handle)
                self._gpu_percent = util.gpu

                mem = self._pynvml.nvmlDeviceGetMemoryInfo(self._gpu_handle)
                self._gpu_mem_percent = (mem.used / mem.total) * 100

                try:
                    self._gpu_temp = self._pynvml.nvmlDeviceGetTemperature(
                        self._gpu_handle, self._pynvml.NVML_TEMPERATURE_GPU
                    )
                except Exception:
                    self._gpu_temp = 0
            except Exception:
                pass

        elif self._gpu_backend == "gputil":
            try:
                gpus = self._gputil.getGPUs()
                if gpus:
                    gpu = gpus[0]
                    self._gpu_percent = gpu.load * 100
                    self._gpu_mem_percent = gpu.memoryUtil * 100
                    self._gpu_temp = gpu.temperature
            except Exception:
                pass

        elif self._gpu_backend == "adl":
            try:
                devices = self._adl.getDevices()
                if devices:
                    self._gpu_percent = 0
                    self._gpu_mem_percent = 0
            except Exception:
                pass

    def get_metrics(self) -> Dict:
        """Retorna las métricas actuales"""
        return {
            "cpu_percent": self._cpu_percent,
            "ram_percent": self._ram_percent,
            "ram_used_gb": self._ram_used_gb,
            "ram_total_gb": self._ram_total_gb,
            "gpu_percent": self._gpu_percent,
            "gpu_mem_percent": self._gpu_mem_percent,
            "gpu_temp": self._gpu_temp,
            "gpu_name": self._gpu_name,
            "gpu_available": self._gpu_backend is not None,
        }

    def has_gpu(self) -> bool:
        return self._gpu_backend is not None


# Instancia global
system_monitor = SystemMonitor()