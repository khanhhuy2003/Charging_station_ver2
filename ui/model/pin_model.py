import random

class PinModel:
    def __init__(self):
        self.current_mode = "Auto"
        self.replace_pin_status = {1: False, 2: False, 3: False, 4: False, 5: False}
        self.active_pin_count = 5  # Ban đầu 5 pin
        # Khởi tạo dữ liệu đầy đủ (bao gồm 13 cell voltage)
        self.pin_data = {
            1: {
                "percent": 92,
                "voltage": 51.8,
                "temp": 33.2,
                "status": "Đang sạc nhanh",
                "SOC" : 100,
                "SOH" : 100,
                "cell_voltages": [round(random.uniform(3.6, 4.2), 3) for _ in range(13)]
            },
            2: {
                "percent": 67,
                "voltage": 50.4,
                "temp": 35.1,
                "status": "Đang sạc",
                "SOC" : 100,
                "SOH" : 100,    
                "cell_voltages": [round(random.uniform(3.6, 4.2), 3) for _ in range(13)]
            },
            3: {
                "percent": 45,
                "voltage": 49.1,
                "temp": 37.8,
                "status": "Ngừng sạc",
                "SOC" : 100,
                "SOH" : 100,
                "cell_voltages": [round(random.uniform(3.6, 4.2), 3) for _ in range(13)]
            },
            4: {
                "percent": 88,
                "voltage": 51.5,
                "temp": 32.4,
                "status": "Đang sạc",
                "SOC" : 100,
                "SOH" : 100,
                "cell_voltages": [round(random.uniform(3.6, 4.2), 3) for _ in range(13)]
            },
            5: {
                "percent": 23,
                "voltage": 48.3,
                "temp": 39.5,
                "status": "Cảnh báo thấp",
                "SOC" : 100,
                "SOH" : 100,
                "cell_voltages": [round(random.uniform(3.6, 4.2), 3) for _ in range(13)]
            }
        }

        self.status_options = [
            ("IDLE", "🤖💤"),
            ("WAITING", "🤖⌛"),
            ("BUSY", "🤖🔄"),
            ("DONE", "🤖🎉")
        ]

    def update_pin(self, pin):
        if self.replace_pin_status[pin]:
            return

        data = self.pin_data[pin]
        data["percent"] = max(0, min(100, data["percent"] + random.randint(-5, 5)))
        data["voltage"] = round(random.uniform(47.0, 52.0), 1)
        data["temp"] = round(random.uniform(30.0, 43.0), 1)

        data["SOC"] = round(random.uniform(47.0, 52.0), 1)
        data["SOH"] = round(random.uniform(30.0, 43.0), 1)


        # Update cell voltages (random lại mỗi lần update)
        data["cell_voltages"] = [round(random.uniform(3.6, 4.2), 3) for _ in range(13)]

        if data["percent"] >= 80:
            data["status"] = "Đang sạc nhanh"
        elif data["percent"] >= 40:
            data["status"] = "Đang sạc"
        elif data["percent"] >= 20:
            data["status"] = "Sạc chậm"
        else:
            data["status"] = "Pin yếu"

    def get_random_status_and_icon(self):
        return random.choice(self.status_options)

    def replace_pin(self, pin):
        self.replace_pin_status[pin] = True
        self.pin_data[pin]["percent"] = 0
        self.pin_data[pin]["status"] = "Đã rút"
        # Cell voltages có thể giữ nguyên hoặc reset tùy ý
        self.pin_data[pin]["cell_voltages"] = [0.0] * 13
        self.pin_data[pin]["SOC"] = 0
        self.pin_data[pin]["SOH"] = 0
        self.active_pin_count -= 1  # Giảm số lượng