"""
Notificaciones vía Telegram
"""
import requests
from datetime import datetime
from typing import Optional


class TelegramNotifier:
    """Envía notificaciones vía bot de Telegram"""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"

    def send_message(self, text: str) -> bool:
        """Envía un mensaje de texto"""
        from utils.config_loader import advanced_config
        timeout = advanced_config.get("telegram_send_timeout", 10)
        try:
            url = f"{self.base_url}/sendMessage"
            response = requests.post(url, json={
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML"
            }, timeout=timeout)
            return response.status_code == 200
        except Exception as e:
            print(f"❌ Error Telegram: {e}")
            return False

    def send_photo(self, image_path: str, caption: str = "") -> bool:
        """Envía una foto"""
        from utils.config_loader import advanced_config
        timeout = advanced_config.get("telegram_photo_timeout", 30)
        try:
            url = f"{self.base_url}/sendPhoto"
            with open(image_path, 'rb') as f:
                response = requests.post(url,
                    data={"chat_id": self.chat_id, "caption": caption},
                    files={"photo": f},
                    timeout=timeout
                )
            return response.status_code == 200
        except Exception as e:
            print(f"❌ Error Telegram: {e}")
            return False

    def send_motion_alert(self, camera_name: str, image_path: Optional[str] = None):
        """Envía alerta de movimiento"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        caption = f"🚨 <b>Movimiento detectado</b>\n📷 Cámara: {camera_name}\n🕐 {timestamp}"

        if image_path:
            self.send_photo(image_path, caption)
        else:
            self.send_message(caption)

    def send_unknown_face_alert(self, camera_name: str, image_path: Optional[str] = None):
        """Envía alerta de rostro desconocido"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        caption = f"👤 <b>Rostro desconocido</b>\n📷 Cámara: {camera_name}\n🕐 {timestamp}"

        if image_path:
            self.send_photo(image_path, caption)
        else:
            self.send_message(caption)