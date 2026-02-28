import zenoh
from pathlib import Path
class ZenohClient:
    def __init__(self):
        zenoh.init_log_from_env_or("error")
        #self.session = zenoh.open(zenoh.Config())
        config = zenoh.Config.from_file(
            "/home/pi/Charging_station_ver2/control/utils/communication/demo_ver_1/config.json5"
        )
        # config_path = Path(__file__).parent / "config.json5"
        # config = zenoh.Config.from_file(str(config_path))    
        self.session = zenoh.open(config)   
    def pub(self, key, msg):
        print(f"📤 PUB {key}")
        self.session.put(key, msg)

    def sub(self, key, cb):
        print(f"📥 SUB {key}")
        self.session.declare_subscriber(key, cb)

    def close(self):
        self.session.close()