import logging
import socket
import threading
import json
import time

DISCOVERY_PORT = 55555
MAGIC_WORD = "AUTOCARD_SERVER"
logger = logging.getLogger(__name__)


class DiscoveryServer:
    def __init__(self, port, room_name="AutoCard Room", password_protected=False):
        self.port = port
        self.room_name = room_name
        self.password_protected = password_protected
        self.running = False
        self.thread = None

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False

    def _run(self):
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
                        # Not used by client if they use addr[0] directly
                        "host": addr[0]
                    }
                    sock.sendto(json.dumps(response).encode('utf-8'), addr)
            except socket.timeout:
                continue
            except Exception as e:
                logger.error(f"Discovery Server Error: {e}")
        sock.close()


class DiscoveryClient:
    def __init__(self):
        self.found_servers = {}
        self.lock = threading.Lock()

    def scan(self, timeout=2.0):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(0.5)

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                # Btoadcast with magic word till respond
                sock.sendto(MAGIC_WORD.encode('utf-8'),
                            ('<broadcast>', DISCOVERY_PORT))

                # Listen for responses for a bit
                listen_start = time.time()
                while time.time() - listen_start < 0.5:
                    try:
                        # addr is the IP address of the sender
                        data, addr = sock.recvfrom(1024)
                        info = json.loads(data.decode('utf-8'))
                        server_ip = addr[0]
                        server_port = info['port']
                        with self.lock:
                            # Store server info with explicit IP from UDP packet source
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

    def get_servers(self):
        with self.lock:
            # Return a simple list of discovered servers
            return list(self.found_servers.values())

    def clear(self):
        with self.lock:
            self.found_servers.clear()
