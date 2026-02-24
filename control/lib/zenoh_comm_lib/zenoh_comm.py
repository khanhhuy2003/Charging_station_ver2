import zenoh

class ZenohClient:
    def __init__(self):
        zenoh.init_log_from_env_or("error")
        self.session = zenoh.open(zenoh.Config())

    def pub(self, key, msg):
        print(f"📤 PUB {key}")
        self.session.put(key, msg)

    def sub(self, key, cb):
        print(f"📥 SUB {key}")
        self.session.declare_subscriber(key, cb)

    def close(self):
        self.session.close()