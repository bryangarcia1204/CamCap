"""
Notificaciones nativas de Windows 10/11

FIX v2:
- plyer como backend PRIMARIO (más estable, sin errores de tipo)
- win11toast como fallback (algunos sistemas lo prefieren)
- win10toast como último recurso
- Logs DEBUG integrados
- Manejo robusto de errores con fallback en cascada
"""
import os
from utils.logger import get_logger
from typing import Optional

logger = get_logger("WindowsNotifier")


class WindowsNotifier:
    """Gestor de notificaciones nativas de Windows"""

    _instance = None
    _available = False
    _backend = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Detecta el mejor backend disponible (plyer primero)"""
        self._win11_toast = None
        self._toaster = None

        # ✅ CAMBIO v2: plyer PRIMERO (más estable)
        try:
            from plyer import notification  # noqa: F401
            self._backend = "plyer"
            self._available = True
            logger.info("✅ Notificaciones: plyer disponible (backend primario)")
            logger.debug(
                "🔔 [init] plyer cargado correctamente, será el backend por defecto"
            )
            return
        except ImportError as e:
            logger.debug(f"🔔 [init] plyer no disponible: {e}")
        except Exception as e:
            logger.debug(f"🔔 [init] plyer error inesperado: {e}")

        # Fallback: win11toast
        try:
            from win11toast import toast
            self._win11_toast = toast
            self._backend = "win11toast"
            self._available = True
            logger.info("✅ Notificaciones: win11toast disponible (fallback)")
            logger.debug(
                "🔔 [init] win11toast cargado, puede fallar en algunos sistemas"
            )
            return
        except ImportError as e:
            logger.debug(f"🔔 [init] win11toast no disponible: {e}")
        except Exception as e:
            logger.debug(f"🔔 [init] win11toast error inesperado: {e}")

        # Fallback final: win10toast
        try:
            from win10toast import ToastNotifier
            self._toaster = ToastNotifier()
            self._backend = "win10toast"
            self._available = True
            logger.info("⚠️ Notificaciones: win10toast disponible (deprecated)")
            logger.debug(
                "🔔 [init] win10toast cargado (deprecated, puede fallar en Py 3.13)"
            )
            return
        except ImportError as e:
            logger.debug(f"🔔 [init] win10toast no disponible: {e}")
        except Exception as e:
            logger.debug(f"🔔 [init] win10toast error inesperado: {e}")

        logger.warning("⚠️ Notificaciones: ninguna librería disponible")
        logger.debug(
            "🔔 [init] Instala alguna: pip install plyer\n"
            "     pip install win11toast\n"
            "     pip install win10toast"
        )
        self._available = False

    def notify(self, title: str, message: str,
               duration: int = 5, icon_path: Optional[str] = None) -> bool:
        """Muestra una notificación nativa."""
        if duration is None:
            from utils.config_loader import advanced_config
            duration = advanced_config.get("windows_notification_duration", 5)

        if not self._available:
            logger.info(f"📢 [{title}] {message}")
            return False

        safe_title = str(title) if title is not None else "ProCamera"
        safe_message = str(message) if message is not None else ""

        safe_icon = None
        if icon_path and isinstance(icon_path, str) and os.path.exists(icon_path):
            safe_icon = icon_path

        logger.debug(
            f"🔔 [notify] Enviando: backend={self._backend}, "
            f"title='{safe_title[:40]}', "
            f"msg_len={len(safe_message)}, duration={duration}s, "
            f"icon={'OK' if safe_icon else 'none'}"
        )

        try:
            if self._backend == "plyer":
                result = self._try_plyer(safe_title, safe_message, duration, safe_icon)
                if result:
                    return True
                logger.debug("🔔 [notify] plyer falló, intentando win11toast...")
                return self._try_win11toast(safe_title, safe_message, duration, safe_icon)

            elif self._backend == "win11toast" and self._win11_toast is not None:
                result = self._try_win11toast(safe_title, safe_message, duration, safe_icon)
                if result:
                    return True
                logger.debug("🔔 [notify] win11toast falló, intentando plyer...")
                return self._try_plyer(safe_title, safe_message, duration, safe_icon)

            elif self._backend == "win10toast" and self._toaster is not None:
                return self._try_win10toast(safe_title, safe_message, duration, safe_icon)

        except Exception as e:
            logger.error(f"❌ [notify] Error general: {type(e).__name__}: {e}")
            return False

        return False

    # ==================== BACKENDS ====================

    def _try_plyer(self, title: str, message: str,
                   duration: int, icon_path: Optional[str]) -> bool:
        try:
            from plyer import notification

            notification.notify(
                title=title,
                message=message[:250],
                app_name="ProCamera",
                app_icon=icon_path,
                timeout=duration,
            )

            logger.debug(f"🔔 [plyer] Notificación enviada OK")
            return True

        except Exception as e:
            logger.debug(f"🔔 [plyer] Falló: {type(e).__name__}: {e}")
            return False

    def _try_win11toast(self, title: str, message: str,
                        duration: int, icon_path: Optional[str]) -> bool:
        if self._win11_toast is None:
            return False

        try:
            kwargs = {"duration": duration}

            if icon_path:
                ext = os.path.splitext(icon_path)[1].lower()
                if ext in ('.ico', '.png', '.jpg', '.jpeg'):
                    kwargs["icon"] = icon_path

            self._win11_toast(title, message, **kwargs)

            logger.debug(f"🔔 [win11toast] Notificación enviada OK")
            return True

        except Exception as e:
            logger.debug(f"🔔 [win11toast] Falló: {type(e).__name__}: {e}")
            return False

    def _try_win10toast(self, title: str, message: str,
                        duration: int, icon_path: Optional[str]) -> bool:
        if self._toaster is None:
            return False

        try:
            self._toaster.show_toast(
                title,
                message[:250],
                icon_path=icon_path,
                duration=duration,
                threaded=True,
            )
            logger.debug(f"🔔 [win10toast] Notificación enviada OK")
            return True

        except Exception as e:
            logger.debug(f"🔔 [win10toast] Falló: {type(e).__name__}: {e}")
            return False

    # ==================== MÉTODOS ESPECÍFICOS ====================

    def notify_motion(self, camera_name: str, image_path: Optional[str] = None) -> bool:
        logger.debug(
            f"🔔 [motion] Notificando: camera='{camera_name}', "
            f"image={'OK' if image_path else 'none'}"
        )
        return self.notify(
            title=f"🚨 Movimiento detectado - {camera_name}",
            message=f"Se detectó movimiento en {camera_name}. Revisa la captura.",
            duration=5,
        )

    def notify_face_unknown(self, camera_name: str) -> bool:
        logger.debug(
            f"🔔 [face_unknown] Notificando: camera='{camera_name}'"
        )
        return self.notify(
            title=f"👤 Rostro desconocido - {camera_name}",
            message=f"Se detectó una persona desconocida en {camera_name}",
            duration=5,
        )

    def notify_face_known(self, camera_name: str, person_name: str) -> bool:
        logger.debug(
            f"🔔 [face_known] Notificando: camera='{camera_name}', "
            f"person='{person_name}'"
        )
        return self.notify(
            title=f"✅ {person_name} detectado",
            message=f"{person_name} está en {camera_name}",
            duration=3,
        )


# Instancia global
windows_notifier = WindowsNotifier()