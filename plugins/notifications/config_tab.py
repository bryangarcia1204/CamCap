"""
Tab de configuración del plugin notifications.

Incluye:
- Notificaciones Windows (on/off, duración)
- Notificaciones Telegram (on/off, token, chat_id)
- Cooldown y timeouts
"""
from PySide6.QtWidgets import (
    QVBoxLayout, QGridLayout, QGroupBox, QLabel,
    QLineEdit, QPushButton, QSpinBox, QCheckBox,
    QScrollArea, QWidget, QMessageBox
)
from PySide6.QtCore import Qt

from ui.settings.settings_dialog_base import PluginConfigTab


class NotificationsConfigTab(PluginConfigTab):
    """Configuración completa del sistema de notificaciones."""

    SCHEMA = {
        "notification_min_interval": {"type": "int", "default": 30},
        "telegram_send_timeout": {"type": "int", "default": 10},
        "telegram_photo_timeout": {"type": "int", "default": 30},
        "windows_notification_duration": {"type": "int", "default": 5},
    }

    def build_ui(self):
        if self.context.settings is not None:
            self.context.settings.register_config_schema(
                self.plugin_name, self.SCHEMA
            )

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)

        # ============ Windows ============
        win_group = QGroupBox("🪟 Notificaciones Windows")
        win_layout = QVBoxLayout(win_group)

        self.windows_enabled_cb = QCheckBox(
            "Activar notificaciones nativas de Windows"
        )
        win_layout.addWidget(self.windows_enabled_cb)

        win_layout.addWidget(QLabel("Duración (segundos):"))
        self.win_duration_spin = QSpinBox()
        self.win_duration_spin.setRange(1, 60)
        self.win_duration_spin.setSuffix(" s")
        win_layout.addWidget(self.win_duration_spin)

        layout.addWidget(win_group)

        # ============ Telegram ============
        tg_group = QGroupBox("📱 Telegram")
        tg_layout = QGridLayout(tg_group)
        tg_layout.setVerticalSpacing(10)
        tg_layout.setHorizontalSpacing(20)

        self.telegram_enabled_cb = QCheckBox("Activar notificaciones por Telegram")
        tg_layout.addWidget(self.telegram_enabled_cb, 0, 0, 1, 2)

        tg_layout.addWidget(QLabel("Token del Bot:"), 1, 0)
        self.telegram_token_edit = QLineEdit()
        self.telegram_token_edit.setEchoMode(QLineEdit.Password)
        tg_layout.addWidget(self.telegram_token_edit, 1, 1)

        tg_layout.addWidget(QLabel("Chat ID:"), 2, 0)
        self.telegram_chat_edit = QLineEdit()
        tg_layout.addWidget(self.telegram_chat_edit, 2, 1)

        test_btn = QPushButton("🧪 Probar notificación")
        test_btn.clicked.connect(self._test_telegram)
        tg_layout.addWidget(test_btn, 3, 0, 1, 2)

        info_label = QLabel(
            "💡 Cómo obtener:\n"
            "1. @BotFather en Telegram → /newbot\n"
            "2. Copia el token\n"
            "3. Envía un mensaje al bot\n"
            "4. Visita: https://api.telegram.org/bot<TOKEN>/getUpdates\n"
            "5. Copia el 'chat_id'"
        )
        info_label.setStyleSheet("color: rgba(255,255,255,0.6); font-size: 11px;")
        info_label.setWordWrap(True)
        tg_layout.addWidget(info_label, 4, 0, 1, 2)

        layout.addWidget(tg_group)

        # ============ Cooldown y timeouts ============
        timing_group = QGroupBox("⏱️ Cooldown y Timeouts")
        timing_layout = QGridLayout(timing_group)
        timing_layout.setVerticalSpacing(10)
        timing_layout.setHorizontalSpacing(20)

        timing_layout.addWidget(QLabel("Cooldown notificaciones:"), 0, 0)
        self.cooldown_spin = QSpinBox()
        self.cooldown_spin.setRange(5, 600)
        self.cooldown_spin.setSingleStep(5)
        self.cooldown_spin.setSuffix(" s")
        timing_layout.addWidget(self.cooldown_spin, 0, 1)

        timing_layout.addWidget(QLabel("Timeout Telegram texto:"), 1, 0)
        self.telegram_text_timeout_spin = QSpinBox()
        self.telegram_text_timeout_spin.setRange(5, 120)
        self.telegram_text_timeout_spin.setSuffix(" s")
        timing_layout.addWidget(self.telegram_text_timeout_spin, 1, 1)

        timing_layout.addWidget(QLabel("Timeout Telegram foto:"), 2, 0)
        self.telegram_photo_timeout_spin = QSpinBox()
        self.telegram_photo_timeout_spin.setRange(5, 300)
        self.telegram_photo_timeout_spin.setSuffix(" s")
        timing_layout.addWidget(self.telegram_photo_timeout_spin, 2, 1)

        layout.addWidget(timing_group)
        layout.addStretch()

        scroll.setWidget(content)
        self.layout.addWidget(scroll)

        self._load_values()

    # ==================== TEST TELEGRAM ====================

    def _test_telegram(self):
        token = self.telegram_token_edit.text().strip()
        chat_id = self.telegram_chat_edit.text().strip()
        if not token or not chat_id:
            QMessageBox.warning(self, "Error", "Token y Chat ID requeridos")
            return
        try:
            import requests
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            response = requests.post(url, json={
                "chat_id": chat_id, "text": "🧪 Prueba desde ProCamera"
            }, timeout=10)
            if response.status_code == 200:
                QMessageBox.information(self, "Éxito", "✅ Notificación enviada")
            else:
                QMessageBox.warning(self, "Error", f"Error: {response.status_code}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error: {e}")

    # ==================== CARGA / GUARDADO ====================

    def _load_values(self):
        try:
            from core.settings_manager import settings_manager
            from utils.config_loader import advanced_config

            # Notificaciones (QSettings)
            notif = settings_manager.get_notification_settings()
            self.telegram_enabled_cb.setChecked(
                notif.get("telegram_enabled", False)
            )
            self.telegram_token_edit.setText(notif.get("telegram_token", ""))
            self.telegram_chat_edit.setText(notif.get("telegram_chat_id", ""))

            # Detección: notify_windows (en detection_settings)
            det = settings_manager.get_detection_settings()
            self.windows_enabled_cb.setChecked(det.get("notify_windows", True))

            # Advanced config
            cfg = advanced_config.get_all()
            self.cooldown_spin.setValue(cfg.get("notification_min_interval", 30))
            self.telegram_text_timeout_spin.setValue(
                cfg.get("telegram_send_timeout", 10)
            )
            self.telegram_photo_timeout_spin.setValue(
                cfg.get("telegram_photo_timeout", 30)
            )
            self.win_duration_spin.setValue(
                cfg.get("windows_notification_duration", 5)
            )
        except Exception as e:
            print(f"Error cargando valores de notifications: {e}")

    def get_config(self):
        return {
            "telegram_enabled": self.telegram_enabled_cb.isChecked(),
            "telegram_token": self.telegram_token_edit.text().strip(),
            "telegram_chat_id": self.telegram_chat_edit.text().strip(),
            "notification_min_interval": self.cooldown_spin.value(),
            "telegram_send_timeout": self.telegram_text_timeout_spin.value(),
            "telegram_photo_timeout": self.telegram_photo_timeout_spin.value(),
            "windows_notification_duration": self.win_duration_spin.value(),
        }

    def apply_changes(self) -> bool:
        try:
            from core.settings_manager import settings_manager
            from utils.config_loader import advanced_config

            # Notificaciones (QSettings)
            settings_manager.save_notification_settings({
                "telegram_enabled": self.telegram_enabled_cb.isChecked(),
                "telegram_token": self.telegram_token_edit.text().strip(),
                "telegram_chat_id": self.telegram_chat_edit.text().strip(),
            })

            # notify_windows va a detection_settings
            det = settings_manager.get_detection_settings()
            det["notify_windows"] = self.windows_enabled_cb.isChecked()
            settings_manager.save_detection_settings(det)

            # Advanced config
            advanced = settings_manager.get_advanced_settings()
            advanced.update({
                "notification_min_interval": self.cooldown_spin.value(),
                "telegram_send_timeout": self.telegram_text_timeout_spin.value(),
                "telegram_photo_timeout": self.telegram_photo_timeout_spin.value(),
                "windows_notification_duration": self.win_duration_spin.value(),
            })
            settings_manager.save_advanced_settings(advanced)
            advanced_config.reload()

            # Recargar NotificationManager
            try:
                from plugins.notifications.notification_manager import notification_manager
                notification_manager._load_telegram_config()
            except Exception as e:
                print(f"Error recargando notification_manager: {e}")

            return True
        except Exception as e:
            print(f"Error aplicando config de notifications: {e}")
            return False