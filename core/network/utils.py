import logging
import socket
import urllib.parse
import socketio

logger = logging.getLogger(__name__)


def run_socketio_server(host, port, password, sub_queue, out_queue):
    """Entry point for the server child process."""
    from threading import Thread as _Thread
    from werkzeug.serving import run_simple

    sio = socketio.Server(cors_allowed_origins="*", async_mode="threading")
    app = socketio.WSGIApp(sio)

    def _bridge():
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

    _Thread(target=_bridge, daemon=True).start()

    @sio.on("synchronize")
    def on_synchronize(sid, data):
        sub_queue.put({"synchronize": data})

    @sio.event
    def connect(sid, environ):
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
    def disconnect(sid):
        sub_queue.put({"disconnected": {}})

    logging.getLogger("GameEngine").info(f"Server listening on {host}:{port}")
    run_simple(host, port, app, threaded=True, use_reloader=False)


def extract_password(environ: dict) -> str | None:
    if "HTTP_AUTHORIZATION" in environ:
        return environ["HTTP_AUTHORIZATION"].replace("Bearer ", "")
    if "QUERY_STRING" in environ:
        params = urllib.parse.parse_qs(environ["QUERY_STRING"])
        return params.get("password", [None])[0]
    return None


def resolve_to_localhost_if_self(host: str) -> str:
    """Return 'localhost' when the target IP belongs to this machine."""
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
