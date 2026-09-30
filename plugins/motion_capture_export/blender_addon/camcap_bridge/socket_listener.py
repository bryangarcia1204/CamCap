"""
Listener de socket en un hilo separado.

Thread-safe: guarda el último frame en una variable global protegida
por lock. El hilo principal de Blender lo lee desde un timer.

NO toca bpy.data desde este hilo.
"""
import socket
import json
import threading
import time
from typing import Optional, Dict, Any

# ============================================================
# ESTADO GLOBAL (thread-safe)
# ============================================================

_lock = threading.RLock()
_listener_thread: Optional[threading.Thread] = None
_running = False

# Estado del socket
_socket: Optional[socket.socket] = None
_connected = False
_host = "127.0.0.1"
_port = 9999

# Último frame recibido (se sobreescribe cada vez)
_last_frame: Optional[Dict[str, Any]] = None
_last_frame_time = 0.0
_frame_count = 0
_error_count = 0

# Callbacks (invocados desde el hilo del listener)
_on_connected_callback = None
_on_disconnected_callback = None


# ============================================================
# API PÚBLICA
# ============================================================

def start_listener_thread():
    """Arranca el hilo del listener (una sola vez)."""
    global _listener_thread, _running

    if _running and _listener_thread is not None and _listener_thread.is_alive():
        return

    _running = True
    _listener_thread = threading.Thread(
        target=_listener_loop,
        daemon=True,
        name="CamCapBridgeListener",
    )
    _listener_thread.start()
    print("🌐 CamCap Bridge: listener thread arrancado")


def stop_listener_thread():
    """Detiene el hilo del listener."""
    global _running
    _running = False
    disconnect()


def connect(host: str, port: int,
            on_connected=None, on_disconnected=None) -> bool:
    """
    Solicita conexión al servidor.

    Returns:
        True si la conexión se inició (aún puede fallar después).
    """
    global _host, _port, _on_connected_callback, _on_disconnected_callback

    with _lock:
        _host = host
        _port = port
        _on_connected_callback = on_connected
        _on_disconnected_callback = on_disconnected

    return True


def disconnect():
    """Cierra la conexión actual."""
    global _socket, _connected

    with _lock:
        sock = _socket
        _socket = None
        _connected = False

    if sock is not None:
        try:
            sock.close()
        except Exception:
            pass

    print("🔌 CamCap Bridge: desconectado")


def is_connected() -> bool:
    """True si hay conexión activa."""
    with _lock:
        return _connected


def get_last_frame() -> Optional[Dict[str, Any]]:
    """
    Retorna el último frame recibido (o None).

    Thread-safe. El hilo principal de Blender llama a esto
    desde su timer.
    """
    with _lock:
        return _last_frame


def get_stats() -> Dict[str, Any]:
    """Stats de la conexión."""
    with _lock:
        return {
            "connected": _connected,
            "host": _host,
            "port": _port,
            "frame_count": _frame_count,
            "error_count": _error_count,
            "last_frame_time": _last_frame_time,
        }


# ============================================================
# LOOP DEL LISTENER (corre en su propio hilo)
# ============================================================

def _listener_loop():
    """Bucle principal del listener."""
    global _socket, _connected, _last_frame, _last_frame_time
    global _frame_count, _error_count

    buffer = b""

    while _running:
        # Si no estamos conectados, intentar conectar
        if _socket is None:
            try:
                with _lock:
                    host = _host
                    port = _port

                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3.0)
                sock.connect((host, port))
                sock.settimeout(1.0)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

                with _lock:
                    _socket = sock
                    _connected = True
                    buffer = b""

                print(f"🔗 CamCap Bridge: conectado a {host}:{port}")

                # Notificar
                if _on_connected_callback:
                    try:
                        _on_connected_callback((host, port))
                    except Exception as e:
                        print(f"Error en on_connected: {e}")

            except Exception as e:
                # No se pudo conectar, esperar y reintentar
                time.sleep(1.0)
                continue

        # Leer datos del socket
        try:
            with _lock:
                sock = _socket

            if sock is None:
                continue

            data = sock.recv(8192)
            if not data:
                # El servidor cerró la conexión
                _handle_disconnect()
                continue

            buffer += data

            # Procesar líneas completas (JSON newline-delimited)
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue

                try:
                    frame = json.loads(line.decode("utf-8"))

                    with _lock:
                        _last_frame = frame
                        _last_frame_time = time.time()

                        if frame.get("type") == "frame":
                            _frame_count += 1

                except json.JSONDecodeError as e:
                    with _lock:
                        _error_count += 1
                    print(f"⚠️ CamCap Bridge: JSON inválido: {e}")
                except Exception as e:
                    with _lock:
                        _error_count += 1
                    print(f"⚠️ CamCap Bridge: error procesando frame: {e}")

        except socket.timeout:
            # Timeout normal, seguir leyendo
            continue
        except (ConnectionResetError, BrokenPipeError, OSError):
            _handle_disconnect()
            continue
        except Exception as e:
            print(f"⚠️ CamCap Bridge: error en recv: {e}")
            _handle_disconnect()
            continue

    # Al salir, cerrar
    _handle_disconnect()
    print("🌐 CamCap Bridge: listener thread detenido")


def _handle_disconnect():
    """Maneja la desconexión del servidor."""
    global _socket, _connected, _last_frame

    with _lock:
        sock = _socket
        _socket = None
        _connected = False
        _last_frame = None
        callback = _on_disconnected_callback
        host = _host
        port = _port

    if sock is not None:
        try:
            sock.close()
        except Exception:
            pass

        print(f"🔌 CamCap Bridge: desconectado de {host}:{port}")

        if callback:
            try:
                callback((host, port))
            except Exception as e:
                print(f"Error en on_disconnected: {e}")