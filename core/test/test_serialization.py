import json
import socketio
import threading
import time
from typing import Any

from core.logic.game_engine import GameEngine
from core.data.player import Player

HOST = "0.0.0.0"
PORT = 5000
SERVER_URL = f"http://{HOST}:{PORT}"


def create_engine(p1_name: str, p2_name: str) -> GameEngine:
    """Creates a GameEngine instance with two players.

    Args:
        p1_name: Name of the first player.
        p2_name: Name of the second player.

    Returns:
        A configured GameEngine instance.
    """
    p1 = Player(player_index=0, name=p1_name)
    p2 = Player(player_index=1, name=p2_name, is_opponent=True)

    return GameEngine([p1, p2])


def server() -> None:
    """Starts the game engine server."""
    sio = socketio.Server(cors_allowed_origins="*")
    app = socketio.WSGIApp(sio)

    engine = create_engine("3", "4")
    engine.start_game()

    @sio.event
    def connect(sid: str, environ: Any) -> None:
        print(f"[SERVER] Client connected: {sid}")

        serialized = engine.serialize()

        sio.emit(
            "game_state",
            serialized,
            to=sid
        )

    @sio.event
    def disconnect(sid: str) -> None:
        print(f"[SERVER] Client disconnected: {sid}")

    from werkzeug.serving import run_simple
    print(f"[SERVER] Running on :{PORT}")
    run_simple(HOST, PORT, app, threaded=True, use_reloader=False)


def client() -> None:
    """Connects to the server and prints received game state."""
    sio = socketio.Client()

    engine = create_engine("1", "2")

    @sio.event
    def connect() -> None:
        print("[CLIENT] Connected")

    @sio.event
    def disconnect() -> None:
        print("[CLIENT] Disconnected")

    @sio.event
    def game_state(data: Any) -> None:
        print("[CLIENT] Received game state")

        engine.deserialize(data)

        serialized = engine.serialize()

        print(json.dumps(serialized, indent=2))

    sio.connect(SERVER_URL)


if __name__ == "__main__":
    server_thread = threading.Thread(target=server, daemon=True)
    server_thread.start()

    time.sleep(2)

    client()
