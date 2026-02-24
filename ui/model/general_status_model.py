import random
from enum import Enum


class Status(Enum):
    IDLE = "🤖💤"
    WAITING = "🤖⌛"
    BUSY = "🤖🔄"
    ERROR = "🤖❌"
    DONE = "🤖🎉"


class Server(Enum):
    CONNECTED = 0
    NOT_CONNECTED = 1


class Wifi(Enum):
    CONNECTED = 0
    CONNECTING = 1
    NOT_CONNECTED = 2


class OpMode(Enum):
    AUTO = 0
    MANUAL = 1


class General_Status_Model:
    def __init__(self):
        self.status_values = Status.IDLE
        self.opmode_value = OpMode.AUTO
        self.no_pin_value = 5
        self.server_connect = Server.NOT_CONNECTED
        self.wifi_value = Wifi.NOT_CONNECTED

    # status
    def set_status_value(self):
        self.status_values = random.choice(list(Status))
        return self.status_values

    # opmode
    def set_opmode_value(self):
        self.opmode_value = random.choice(list(OpMode))
        return self.opmode_value

    # number of pin
    def set_no_pin_value(self, value: int):
        self.no_pin_value = value
        return self.no_pin_value
    def get_no_pin(self):
        return self.no_pin_value
    # server connection
    def set_server_connect(self):
        self.server_connect = random.choice(list(Server))
        return self.server_connect
    # wifi status
    def set_wifi_value(self):
        self.wifi_value = random.choice(list(Wifi))
        return self.wifi_value





