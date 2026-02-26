import socket
import json


class UDPClient:
    def __init__(self, esp_ip, esp_port):
        self.esp_addr = (esp_ip, esp_port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(2)

    def send(self, data: dict):
        payload = json.dumps(data).encode()
        self.sock.sendto(payload, self.esp_addr)

    def recv(self):
        try:
            data, _ = self.sock.recvfrom(1024)
            return json.loads(data.decode())
        except Exception:
            return None