from lib.zenoh_comm_lib.zenoh_comm import ZenohClient
from utils.var_shared_utils import RobotSendData, ChargerSendData
import threading
import socket
#Bao gồm 2 phần
# + Nhan data từ robot qua zenoh
# + Sau khi nhan du lieu từ zenoh, gửi UDP tới ESP32 và ngược lại

class Charger_Ver1:
    def __init__(self):
        # ---- Shared data ----
        self.robot_data = RobotSendData()
        self.charger_data = ChargerSendData()

        # ---- Zenoh ----
        self.zenoh = ZenohClient()
        self.zenoh.subscribe(
            key="robot/status",
            callback=self.zenoh_rx_from_robot
        )

        # ---- UDP ----
        self.udp_ip_esp32 = "192.168.1.50"
        self.udp_port_esp32 = 5005

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("", 5006))

        self.udp_thread = threading.Thread(
            target=self.udp_rx_from_esp32,
            daemon=True
        )
        self.udp_thread.start()
    
    def zenoh_rx_from_robot(self, sample): #(Robot → Pi)
        raw = bytes(sample.payload)
        self.robot_data.decode(raw)
        self.udp_tx_to_esp32(self.robot_data)    

    def zenoh_tx_to_robot(self, data: ChargerSendData):
        payload = data.encode()
        self.zenoh.pub("charger/status", payload)    

    def udp_rx_from_esp32(self):
        while True:
            data, addr = self.sock.recvfrom(1024)
            self.charger_data.decode(data)
            self.zenoh_tx_to_robot(self.charger_data)
            
    def udp_tx_to_esp32(self, data: RobotSendData):
        payload = data.encode()
        self.sock.sendto(
            payload,
            (self.udp_ip_esp32, self.udp_port_esp32)
        )    

