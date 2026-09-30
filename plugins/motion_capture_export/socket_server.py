"""
Servidor TCP para enviar landmarks a Blender en tiempo real.

Protocolo: JSON por líneas (newline-delimited JSON).
Cada mensaje es un JSON en una sola línea terminado en \n.

Mensajes:
  - hello:    primer mensaje al conectar
  - frame:    landmarks de un frame
  - bye:      cierre limpio

Formato de 'frame':
  {
    "type": "frame",
    "frame_index": 42,
    "timestamp": 1.4,
    "fps": 15.0,
    "person": {
      "track_id": 0,
      "bbox": [x, y, w, h],
      "confidence": 0.87,
      "landmarks": [[x, y, z, vis], ...33...]
    }
  }

Si hay varias personas, se envían múltiples mensajes 'frame'
con el mismo frame_index.
"""
import socket
import json
import threading
import time
from typing import Optional, Callable

from utils.logger import get_logger

logger = get_logger("Plugin.SocketServer")


class SocketServer:
    """
    Servidor TCP que acepta UNA conexión y le envía frames.

    Uso:
        server = SocketServer(port=9999)
        server.start()
        # Cuando Blender se conecte:
        server.send_frame({
            "type": "frame",
            "frame_index": 0,
            "landmarks": [...],
        })
        server.stop()
    """

    DEFAULT_PORT = 9999
    DEFAULT_HOST = "127.0.0.1"

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        on_client_connected: Optional[Callable] = None,
        on_client_disconnected: Optional[Callable] = None,
    ):
        self.host = host
        self.port = port
        self.on_client_connected = on_client_connected
        self.on_client_disconnected = on_client_disconnected

        self._server_socket: Optional[socket.socket] = None
        self._client_socket: Optional[socket.socket] = None
        self._client_address: Optional[tuple] = None
        self._accept_thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.RLock()

        self._frames_sent = 0
        self._send_errors = 0

    # ==================== START/STOP ====================

    def start(self) -> bool:
        """Arranca el servidor y empieza a aceptar conexiones."""
        if self._running:
            logger.debug("SocketServer ya está corriendo")
            return True

        try:
            self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_socket.bind((self.host, self.port))
            self._server_socket.listen(1)
            self._server_socket.settimeout(1.0)

            self._running = True
            self._accept_thread = threading.Thread(
                target=self._accept_loop,
                daemon=True,
                name="SocketServerAccept",
            )
            self._accept_thread.start()

            logger.info(f"🌐 SocketServer escuchando en {self.host}:{self.port}")
            return True

        except OSError as e:
            if e.errno == 98 or e.errno == 10048:  # Address already in use
                logger.error(f"❌ Puerto {self.port} ya está en uso")
            else:
                logger.error(f"❌ Error arrancando servidor: {e}")
            self._server_socket = None
            return False
        except Exception as e:
            logger.error(f"❌ Error arrancando servidor: {e}", exc_info=True)
            return False

    def stop(self):
        """Detiene el servidor y cierra la conexión."""
        self._running = False

        # Enviar bye al cliente
        if self._client_socket is not None:
            try:
                self._send_message({"type": "bye"})
            except Exception:
                pass

        with self._lock:
            # Cerrar cliente
            if self._client_socket is not None:
                try:
                    self._client_socket.close()
                except Exception:
                    pass
                self._client_socket = None
                self._client_address = None

            # Cerrar servidor
            if self._server_socket is not None:
                try:
                    self._server_socket.close()
                except Exception:
                    pass
                self._server_socket = None

        if self._accept_thread is not None:
            self._accept_thread.join(timeout=2.0)
            self._accept_thread = None

        logger.info(
            f"🌐 SocketServer detenido "
            f"({self._frames_sent} frames enviados, "
            f"{self._send_errors} errores)"
        )

    # ==================== ACEPT LOOP ====================

    def _accept_loop(self):
        """Acepta una conexión y espera a que se cierre."""
        while self._running:
            try:
                if self._server_socket is None:
                    break

                client, address = self._server_socket.accept()
                client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

                with self._lock:
                    if self._client_socket is not None:
                        # Ya hay un cliente, rechazar el nuevo
                        logger.warning(
                            f"⚠️ Ya hay un cliente conectado, "
                            f"rechazando {address}"
                        )
                        try:
                            client.close()
                        except Exception:
                            pass
                        continue

                    self._client_socket = client
                    self._client_address = address

                logger.info(f"🔗 Cliente conectado: {address}")
                self._send_hello()

                if self.on_client_connected:
                    try:
                        self.on_client_connected(address)
                    except Exception as e:
                        logger.debug(f"Error en on_client_connected: {e}")

                # Esperar a que el cliente se desconecte
                self._wait_for_disconnect()

            except socket.timeout:
                continue
            except OSError as e:
                if self._running:
                    logger.debug(f"Socket accept: {e}")
                break
            except Exception as e:
                if self._running:
                    logger.error(f"❌ Error en accept_loop: {e}")
                break

    def _wait_for_disconnect(self):
        """Espera a que el cliente se desconecte."""
        client = self._client_socket
        if client is None:
            return

        try:
            client.settimeout(1.0)
            while self._running:
                try:
                    data = client.recv(4096)
                    if not data:
                        break
                    # Ignorar datos del cliente (no esperamos nada)
                except socket.timeout:
                    continue
                except Exception:
                    break
        finally:
            self._on_client_disconnected()

    def _on_client_disconnected(self):
        """Callback cuando el cliente se desconecta."""
        with self._lock:
            address = self._client_address
            if self._client_socket is not None:
                try:
                    self._client_socket.close()
                except Exception:
                    pass
                self._client_socket = None
                self._client_address = None

        if address:
            logger.info(f"🔌 Cliente desconectado: {address}")

        if self.on_client_disconnected:
            try:
                self.on_client_disconnected(address)
            except Exception as e:
                logger.debug(f"Error en on_client_disconnected: {e}")

    # ==================== ENVÍO ====================

    def is_client_connected(self) -> bool:
        """True si hay un cliente conectado."""
        with self._lock:
            return self._client_socket is not None

    def get_client_address(self) -> Optional[tuple]:
        with self._lock:
            return self._client_address

    def send_frame(self, frame_data: dict) -> bool:
        """
        Envía un frame al cliente.

        Args:
            frame_data: dict con los datos del frame.

        Returns:
            True si se envió correctamente.
        """
        return self._send_message(frame_data)

    def _send_hello(self):
        """Envía el mensaje de bienvenida."""
        from .pose_tracker import HybridPoseTracker

        self._send_message({
            "type": "hello",
            "version": "1.0.0",
            "pipeline": "YOLOv8-Pose + MediaPipe Pose",
            "landmarks_names": HybridPoseTracker.LANDMARK_NAMES,
            "landmarks_count": 33,
        })

    def _send_message(self, data: dict) -> bool:
        """Envía un dict como JSON + newline."""
        with self._lock:
            client = self._client_socket

        if client is None:
            return False

        try:
            line = json.dumps(data, ensure_ascii=False) + "\n"
            client.sendall(line.encode("utf-8"))
            self._frames_sent += 1
            return True
        except (BrokenPipeError, ConnectionResetError):
            logger.debug("Cliente cerró la conexión")
            self._send_errors += 1
            self._on_client_disconnected()
            return False
        except Exception as e:
            logger.debug(f"Error enviando: {e}")
            self._send_errors += 1
            return False

    # ==================== STATS ====================

    def get_stats(self) -> dict:
        return {
            "running": self._running,
            "client_connected": self.is_client_connected(),
            "client_address": self._client_address,
            "frames_sent": self._frames_sent,
            "send_errors": self._send_errors,
            "host": self.host,
            "port": self.port,
        }