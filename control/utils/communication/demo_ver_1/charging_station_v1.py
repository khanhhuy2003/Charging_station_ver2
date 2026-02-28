import socket
import threading
import json
import time
from enum import Enum

from control.lib.zenoh_comm_lib.zenoh_comm import ZenohClient
from control.utils.communication import topics
from control.utils.communication import json_api
#python3 -m control.utils.communication.demo_ver_1.charging_station_v1

class ChargingProgress(Enum):
    DOING_UPPER = "DOING_ABOVE"
    DOING_LOWER = "DOING_BELOW"
    DONE = "DONE"

class ChargingGateway:

    def __init__(self):
        print("🚀 Charging Gateway (Pi TCP Client) Starting...")

        # ---- ESP32 SERVER INFO ----
        self.esp32_ip = "10.162.131.3"
        self.esp32_port = 5001

        self.client_socket = None

        # ---- State ----
        self.progress = ChargingProgress.DOING_UPPER
        self.error_id = 0
        self.error_detail = ""

        self.zenoh = ZenohClient()

        # ---- Connect TCP ----
        self.connect_to_esp32()

        # ---- Start RX Thread ----
        threading.Thread(
            target=self.tcp_rx_from_esp32,
            daemon=True
        ).start()

        # ---- Zenoh ----
        self.zenoh.sub(
            key="charger_1/charger/robot_request",
            cb=self.zenoh_rx_from_robot
        )

    # ==========================================
    # TCP CONNECT
    # ==========================================

    def connect_to_esp32(self):
        while True:
            try:
                print("Connecting to ESP32...")
                self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.client_socket.connect((self.esp32_ip, self.esp32_port))
                print("Connected to ESP32")
                break
            except Exception as e:
                print("Connect failed, retrying...", e)
                time.sleep(2)

    # ==========================================
    # JSON BUILDER
    # ==========================================

    def build_status_json(self):
        msg = {
            "charger_name": "charger_1",
            "charger_MAC": "AA:BB:CC:DD:EE:FF",
            "battery": {
                "1": 0.1,
                "2": 0.2,
                "3": 0.3,
                "4": 0.4,
                "5": 0.5
            },
            "status": "BUSY",
            "charging": {
                "progress": self.progress.name,
                "error": {
                    "id": self.error_id,
                    "detail": self.error_detail
                },
                "estimate_time": 10
            }
        }
        return json.dumps(msg)

    # ==========================================
    # ZENOH RX
    # ==========================================

    def zenoh_rx_from_robot(self, sample):
        raw = sample.payload.to_string()
        print("Robot → Charger:", raw)

        try:
            robot_msg = json.loads(raw)
            request_value = robot_msg.get("request", False)
            esp32_msg = {
                "request": 1 if request_value else 0,
                "upper_sensor_on": robot_msg.get("upper_sensor_on", False),
                "lower_sensor_on": robot_msg.get("lower_sensor_on", False),
                "robot_name": robot_msg.get("robot_name", ""),
                "mac_address": robot_msg.get("mac_address", "")
            }

            payload = json.dumps(esp32_msg)

            self.client_socket.send((payload + "\n").encode())
            print("Charger → ESP32:", payload)

        except Exception as e:
            print("JSON parse error:", e)
    # ==========================================
    # TCP RX
    # ==========================================

    def tcp_rx_from_esp32(self):
        while True:
            try:
                data = self.client_socket.recv(1024)
                if not data:
                    print("ESP32 disconnected")
                    self.connect_to_esp32()
                    continue

                raw = data.decode().strip()
                print("ESP32 → Charger:", raw)

                esp_msg = json.loads(raw)

                if esp_msg.get("doing_above") == 1:
                    self.progress = ChargingProgress.DOING_UPPER

                elif esp_msg.get("doing_below") == 1:
                    self.progress = ChargingProgress.DOING_LOWER

                elif esp_msg.get("success") == 1:
                    self.progress = ChargingProgress.DONE

                self.publish_status()

            except Exception as e:
                print("TCP RX error:", e)
                self.connect_to_esp32()

    # ==========================================
    # ZENOH TX
    # ==========================================

    def publish_status(self):
        payload = self.json_api.build_status_json()
        self.zenoh.pub(
            topics.robot_progress("vinmotion_2"),
            payload
        )
        print("📤 Publish → Robot:", payload)


# ==========================================
# MAIN
# ==========================================

def main():
    gateway = ChargingGateway()
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()