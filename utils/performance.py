"""
Utilidades de rendimiento: pacing, throttling, sleep helpers
"""
import time
from PySide6.QtWidgets import QApplication
from utils.logger import get_logger

logger = get_logger("Performance")


class PacingController:
    """Controla el ritmo de ejecución para evitar picos de CPU"""
    
    @staticmethod
    def sleep_ms(ms: int, process_events: bool = True):
        """
        Pausa no bloqueante que procesa eventos de Qt
        
        Args:
            ms: Milisegundos a esperar
            process_events: Si True, procesa eventos durante el sleep
        """
        if ms <= 0:
            return
        
        if process_events and QApplication.instance():
            start = time.time()
            target = start + (ms / 1000.0)
            
            while time.time() < target:
                QApplication.processEvents()
                remaining = target - time.time()
                if remaining <= 0:
                    break
                time.sleep(min(0.01, remaining))
        else:
            time.sleep(ms / 1000.0)
    
    @staticmethod
    def adaptive_sleep(target_fps: int, last_time: float) -> float:
        """
        Calcula sleep adaptativo para mantener FPS objetivo
        
        Args:
            target_fps: FPS objetivo
            last_time: Timestamp del último frame
        
        Returns:
            Nuevo timestamp después del sleep
        """
        if target_fps <= 0:
            return time.time()
        
        target_frame_time = 1.0 / target_fps
        current_time = time.time()
        elapsed = current_time - last_time
        
        if elapsed < target_frame_time:
            sleep_time = target_frame_time - elapsed
            if sleep_time > 0.05:
                time.sleep(sleep_time * 0.5)
                time.sleep(sleep_time * 0.5)
            else:
                time.sleep(sleep_time)
        
        return time.time()


class CPUMonitor:
    """Monitorea la carga de CPU para ajustar dinámicamente"""
    
    def __init__(self, max_load: float = 0.8):
        self.max_load = max_load
        self._last_check = 0
        self._check_interval = 2.0
        self._last_load = 0.0
        self._skip_frames = 0
    
    def should_skip_frame(self) -> bool:
        """
        Determina si se debe saltar un frame para reducir carga
        Solo funciona si psutil está disponible
        """
        current_time = time.time()
        if current_time - self._last_check < self._check_interval:
            return False
        
        self._last_check = current_time
        
        try:
            import psutil
            self._last_load = psutil.cpu_percent(interval=0.1) / 100.0
            
            if self._last_load > self.max_load:
                self._skip_frames += 1
                return True
            else:
                if self._skip_frames > 0:
                    self._skip_frames -= 1
            
            return False
        except ImportError:
            return False
    
    def get_load(self) -> float:
        """Retorna la última carga medida (0-1)"""
        return self._last_load


class FrameScheduler:
    """Programador de frames para controlar el ritmo"""
    
    def __init__(self, target_fps: int = 30):
        self.target_fps = target_fps
        self.frame_interval = 1.0 / target_fps if target_fps > 0 else 0
        self.last_frame_time = time.time()
        self.dropped_frames = 0
        self.total_frames = 0
    
    def wait_for_next_frame(self) -> bool:
        """
        Espera hasta el próximo frame
        
        Returns:
            True si hay que procesar frame
        """
        current = time.time()
        elapsed = current - self.last_frame_time
        
        if elapsed < self.frame_interval:
            sleep_time = self.frame_interval - elapsed
            time.sleep(sleep_time)
            self.last_frame_time = time.time()
            self.total_frames += 1
            return True
        else:
            self.dropped_frames += 1
            self.last_frame_time = current
            return True
    
    def set_fps(self, fps: int):
        """Cambia FPS dinámicamente"""
        self.target_fps = fps
        self.frame_interval = 1.0 / fps if fps > 0 else 0
    
    def get_stats(self) -> dict:
        """Retorna estadísticas"""
        return {
            "target_fps": self.target_fps,
            "total_frames": self.total_frames,
            "dropped_frames": self.dropped_frames
        }