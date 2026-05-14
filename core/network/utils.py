import logging
import socket
import urllib.parse
from typing import Any, Optional, Dict
import socketio
from werkzeug.serving import run_simple
from threading import Thread

logger = logging.getLogger(__name__)


def run_socketio_server(
    host: str,
    port: int,
    password: Optional[str],
    sub_queue: Any,
    out_queue: Any
) -> None:
    """Starts the SocketIO server in a separate process.

    Args:
        host: The host address to bind to.
        port: The port number to listen on.
        password: An optional password for client connection validation.
        sub_queue: A queue to put events received from clients.
        out_queue: A queue to get events to be sent to clients.
    """
    sio = socketio.Server(cors_allowed_origins="*", async_mode="threading")
    app = socketio.WSGIApp(sio)

    def _bridge() -> None:
        while True:
            try:
                item = out_queue.get()
                if item is None:
                    break
                event, data = item
                sio.emit(event, data)
            except Exception as e:
                print(f"[Server Process] Bridge error: {e}")
                pass

    Thread(target=_bridge, daemon=True).start()

    @sio.on("synchronize")
    def on_synchronize(sid: str, data: Any) -> None:
        sub_queue.put({"synchronize": data})

    @sio.event
    def connect(sid: str, environ: Dict[str, Any]) -> bool:
        print(f"[Server Process] Client {sid} connecting...")
        if password:
            client_pass = extract_password(environ)
            if client_pass != password:
                logger.warning(
                    f"Rejected connection from {sid}: bad password")
                return False
        sub_queue.put({"connected": {}})
        print(f"[Server Process] Client {
              sid} connection signal sent to main process")
        return True

    @sio.event
    def disconnect(sid: str) -> None:
        sub_queue.put({"disconnected": {}})

    logging.getLogger("GameEngine").info(f"Server listening on {host}:{port}")
    run_simple(host, port, app, threaded=True, use_reloader=False)


def extract_password(environ: Dict[str, Any]) -> Optional[str]:
    """Extracts a password from the WSGI environment.

    Args:
        environ: The WSGI environment dictionary.

    Returns:
        The extracted password if present, otherwise None.
    """
    if "HTTP_AUTHORIZATION" in environ:
        return environ["HTTP_AUTHORIZATION"].replace("Bearer ", "")
    if "QUERY_STRING" in environ:
        params = urllib.parse.parse_qs(environ["QUERY_STRING"])
        return params.get("password", [None])[0]
    return None


def resolve_to_localhost_if_self(host: str) -> str:
    """Resolves target IP to 'localhost' if it belongs to the current machine.

    Args:
        host: The target host IP or name.

    Returns:
        'localhost' if the host is local, otherwise the original host string.
    """
    if host in ("localhost", "127.0.0.1"):
        return host
    try:
        hostname = socket.gethostname()
        local_ips = {socket.gethostbyname(hostname)}
        try:
            _, _, ip_list = socket.gethostbyname_ex(hostname)
            local_ips.update(ip_list)
        except Exception:
            pass
        if host in local_ips:
            logging.getLogger("GameEngine").info(
                f"Redirecting {host} → localhost")
            return "localhost"
    except Exception:
        pass
    return host
