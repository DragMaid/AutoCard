import logging
import socket
import threading
import json
import time
from typing import Dict, List, Any, Optional
from core.config import config

DISCOVERY_PORT: int = config.DEFAULT_PORT + 1
MAGIC_WORD: str = "AUTOCARD_SERVER"
logger = logging.getLogger(__name__)


class DiscoveryServer:
    """
    Handles discovery server-side broadcasting.

    Attributes:
        port (int): Port for the game server.
        room_name (str): Name of the room.
        password_protected (bool): Whether the server is password protected.
        running (bool): Whether the discovery server is running.
    """

    def __init__(self, port: int, room_name: str = "AutoCard Room", password_protected: bool = False) -> None:
        """
        Initializes DiscoveryServer.

        Args:
            port (int): Port for the game server.
            room_name (str): Name of the room.
            password_protected (bool): Whether the server is password protected.
        """
        self.port: int = port
        self.room_name: str = room_name
        self.password_protected: bool = password_protected
        self.running: bool = False
        self.thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Starts the discovery server."""
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        """Stops the discovery server."""
        self.running = False

    def _run(self) -> None:
        """Internal loop for discovery server."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, 'SO_REUSEPORT'):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(('', DISCOVERY_PORT))
        sock.settimeout(1.0)

        while self.running:
            try:
                data, addr = sock.recvfrom(1024)
                if data.decode('utf-8') == MAGIC_WORD:
                    response = {
                        "name": self.room_name,
                        "port": self.port,
                        "password": self.password_protected,
                        "host": addr[0]
                    }
                    sock.sendto(json.dumps(response).encode('utf-8'), addr)
            except socket.timeout:
                continue
            except Exception as e:
                logger.error(f"Discovery Server Error: {e}")
        sock.close()


class DiscoveryClient:
    """
    Handles discovery client-side scanning.

    Attributes:
        found_servers (Dict): Dictionary of discovered servers.
    """

    def __init__(self) -> None:
        """Initializes DiscoveryClient."""
        self.found_servers: Dict[tuple[str, int], Any] = {}
        self.lock = threading.Lock()

    def scan(self, timeout: float = 2.0) -> None:
        """
        Scans for available servers.

        Args:
            timeout (float): Scan timeout in seconds.
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(0.5)

        start_time: float = time.time()
        while time.time() - start_time < timeout:
            try:
                sock.sendto(MAGIC_WORD.encode('utf-8'),
                            ('<broadcast>', DISCOVERY_PORT))

                listen_start: float = time.time()
                while time.time() - listen_start < 0.5:
                    try:
                        data, addr = sock.recvfrom(1024)
                        info = json.loads(data.decode('utf-8'))
                        server_ip: str = addr[0]
                        server_port: int = info['port']
                        with self.lock:
                            self.found_servers[(server_ip, server_port)] = {
                                "name": info['name'],
                                "password": info['password'],
                                "host": server_ip,
                                "port": server_port
                            }
                    except socket.timeout:
                        break
            except Exception as e:
                logger.error(f"Discovery Client Error: {e}")
        sock.close()

    def get_servers(self) -> List[Any]:
        """
        Returns list of discovered servers.

        Returns:
            List[Any]: List of server information objects.
        """
        with self.lock:
            return list(self.found_servers.values())

    def clear(self) -> None:
        """Clears discovered servers."""
        with self.lock:
            self.found_servers.clear()
