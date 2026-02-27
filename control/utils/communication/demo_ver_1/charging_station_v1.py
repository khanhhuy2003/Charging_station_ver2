# from control.lib.zenoh_comm_lib.zenoh_comm import ZenohClient
# from control.utils.var_shared_utils import RobotSendData, ChargerSendData
# from control.utils.communication import topics
# from control.utils.communication import json_api
# from control.utils.communication.demo_ver_1.udp_client import UDPClient
# import threading
# import socket
# import sys
# import signal
# import time
# import json
# #Bao gồm 2 phần
# # + Nhan data từ robot qua zenoh
# # + Sau khi nhan du lieu từ zenoh, gửi UDP tới ESP32 và ngược lại
# #python3 -m control.utils.communication.demo_ver_1.charging_station_v1
# from enum import Enum

# class ChargingProgress(Enum):
#     DOING_ABOVE = 1
#     DOING_BELOW = 2
#     DONE = 3
# class Charger_Ver1:
#     def __init__(self):
#         # ---- Shared data ----
#         self.robot_data = RobotSendData()
#         self.charger_data = ChargerSendData()
#         self.udp_client = UDPClient("192,168.1.50", 5005)

#         # ---- Zenoh ----
#         self.zenoh = ZenohClient()
#         self.zenoh.sub(
#             key="charger_1/charger/robot_request",
#             cb=self.zenoh_rx_from_robot
#         )

#         # ---- UDP ----
#         self.udp_ip_esp32 = "192.168.1.50"
#         self.udp_port_esp32 = 5005

#         self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#         self.sock.bind(("", 5006))

#         self.udp_thread = threading.Thread(
#             target=self.udp_rx_from_esp32,
#             daemon=True
#         )
#         self.udp_thread.start()
    
#     def zenoh_rx_from_robot(self, sample): #(Robot → Pi)
#         raw = sample.payload.to_string()
#         print(raw)
#         self.udp_tx_to_esp32(raw)    

#     def zenoh_tx_to_robot(self, data: ChargerSendData):
#         payload = data.encode()
#         self.zenoh.pub(topics.robot_progress("vinmotion_2"), payload)    

#     def udp_rx_from_esp32(self):
#         while True:
#             data, addr = self.sock.recvfrom(1024)
#             self.charger_data.decode(data)
#             self.zenoh_tx_to_robot(self.charger_data)
            
#     def udp_tx_to_esp32(self, data: RobotSendData):
#         payload = data.encode()
#         self.sock.sendto(
#             payload,
#             (self.udp_ip_esp32, self.udp_port_esp32)
#         )    

# def main():
#     print("🚀 Charger_Ver1 (Pi Gateway) starting...")
#     charger = Charger_Ver1()
#     charger_send_data = ChargerSendData()
#     ds = {
#     "charger_name": "charger_1",
#     "charger_MAC": "AA:BB:CC:DD:EE:FF",
#     "battery": {
#         "1": 0.1,
#         "2": 0.2,
#         "3": 0.3,
#         "4": 0.4,
#         "5": 0.5
#     },
#     "status": "BUSY",
#     "charging": {
#         "progress": charger_send_data.progress,   # 🔥 thay đổi liên tục
#         "error": {
#             "id": "",
#             "detail": ""
#         },
#         "estimate_time": 10
#     }
# }   
#     charger_send_data.progress = ChargingProgress.DONE
#     msg = json_api.json_build_charger_response(ds, charger_send_data.progress)


    





# if __name__ == "__main__":
#     main()


import socket
import threading
import json
import time
from enum import Enum

# ==== IMPORT YOUR REAL LIBS ====
from control.lib.zenoh_comm_lib.zenoh_comm import ZenohClient
from control.utils.communication import topics


# ==========================================
# ENUM
# ==========================================

class ChargingProgress(Enum):
    DOING_UPPER = "DOING_ABOVE"
    DOING_LOWER = "DOING_BELOW"
    DONE = "DONE"


# ==========================================
# GATEWAY
# ==========================================

class ChargingGateway:

    def __init__(self):
        print("🚀 Charging Gateway Starting...")

        # ---- Network Config ----
        self.udp_ip = "192.168.1.50"
        self.udp_port = 5005

        # ---- State ----
        self.progress = ChargingProgress.DOING_ABOVE
        self.error_id = ""
        self.error_detail = ""

        # ---- Zenoh ----
        self.zenoh = ZenohClient()
        self.zenoh.sub(
            key="charger_1/charger/robot_request",
            cb=self.zenoh_rx_from_robot
        )

        # ---- UDP ----
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("", 5006))

        threading.Thread(
            target=self.udp_rx_from_esp32,
            daemon=True
        ).start()

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
                "progress": self.progress.value,
                "error": {
                    "id": self.error_id,
                    "detail": self.error_detail
                },
                "estimate_time": 10
            }
        }
        return json.dumps(msg)

    # ==========================================
    # ZENOH CALLBACK    
    # ==========================================

    def zenoh_rx_from_robot(self, sample):
        raw = sample.payload.to_string()
        print("📩 Robot → Charger:", raw)

        try:
            # Parse JSON từ robot
            robot_msg = json.loads(raw)

            request_value = robot_msg.get("request", 0)

            esp32_msg = {
                "request": 1 if request_value else 0
            }

            payload = json.dumps(esp32_msg)

            # Gửi xuống STM32
            self.sock.sendto(
                payload.encode(),
                (self.udp_ip, self.udp_port)
            )
            print("📤 Charger → ESP32:", payload)

        except Exception as e:
            print("❌ JSON parse error:", e)

    def publish_status(self):
        payload = self.build_status_json()
        self.zenoh.pub(
            topics.robot_progress("vinmotion_2"),
            payload
        )
        print("📤 Publish → Robot:", payload)

    # ==========================================
    # UDP RX
    # ==========================================

    def udp_rx_from_esp32(self):
        while True:
            data, _ = self.sock.recvfrom(1024)
            raw = data.decode()
            print("📥 ESP32 → Charger:", raw)

            try:
                esp_msg = json.loads(raw)

                # ===== Mapping trạng thái =====
                if esp_msg.get("doing_above") == 1:
                    self.progress = ChargingProgress.DOING_UPPER

                elif esp_msg.get("doing_below") == 1:
                    self.progress = ChargingProgress.DOING_LOWER

                elif esp_msg.get("success") == 1:
                    self.progress = ChargingProgress.DONE

                # Publish status sau khi update progress
                self.publish_status()

            except Exception as e:
                print("❌ ESP32 JSON error:", e)

    # ==========================================
    # DEMO LOOP (optional)
    # ==========================================

    def demo_cycle(self):
        progress_list = list(ChargingProgress)
        i = 0

        while True:
            self.progress = progress_list[i % len(progress_list)]
            self.publish_status()
            i += 1
            time.sleep(2)


# ==========================================
# MAIN
# ==========================================

def main():
    gateway = ChargingGateway()
    gateway.demo_cycle()


if __name__ == "__main__":
    main()