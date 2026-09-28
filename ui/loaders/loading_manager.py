"""
Gestor unificado para splash screen y loading overlay
Uso simplificado con context manager
"""
from PySide6.QtWidgets import QApplication
from ui.loaders.splash_screen import SplashScreen


class LoadingManager:
    """Gestor singleton de pantallas de carga"""
    
    _instance = None
    _splash = None
    _overlay = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def init_splash(cls) -> 'SplashScreen':
        """Inicializa el splash screen"""
        cls._splash = SplashScreen()
        cls._splash.show_with_animation()
        return cls._splash
    
    @classmethod
    def set_splash_progress(cls, value: int, status: str = None):
        """Actualiza el progreso del splash"""
        if cls._splash:
            cls._splash.set_progress(value, status)
    
    @classmethod
    def finish_splash(cls):
        """Cierra el splash"""
        if cls._splash:
            cls._splash.finish()
            cls._splash = None
    
    @classmethod
    def init_overlay(cls, parent):
        """Inicializa el overlay para una ventana"""
        from ui.loaders.loading_overlay import LoadingOverlay
        cls._overlay = LoadingOverlay(parent)
        return cls._overlay
    
    @classmethod
    def show_loading(cls, text: str = "Cargando...", 
                    detail: str = "",
                    indeterminate: bool = True):
        """Muestra el overlay de carga"""
        if cls._overlay:
            cls._overlay.show_overlay(text, detail, indeterminate)
    
    @classmethod
    def update_loading(cls, progress: int, text: str = None):
        """Actualiza el progreso"""
        if cls._overlay:
            cls._overlay.update_progress(progress, text)
    
    @classmethod
    def hide_loading(cls):
        """Oculta el overlay"""
        if cls._overlay:
            cls._overlay.hide_overlay()


class LoadingContext:
    """Context manager para operaciones con overlay automático"""
    
    def __init__(self, text: str = "Cargando...", detail: str = ""):
        self.text = text
        self.detail = detail
    
    def __enter__(self):
        LoadingManager.show_loading(self.text, self.detail)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        LoadingManager.hide_loading()
        return False