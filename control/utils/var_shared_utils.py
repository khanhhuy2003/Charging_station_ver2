#pin
class RobotSendData:
    def __init__(self):
        self.request = 0
        self.upper_sensor_on = 0
        self.lower_sensor_on = 0
class ChargerSendData:
    def __init__(self):
        self.progress = None
        self.error_id = 0
        self.detail = None
