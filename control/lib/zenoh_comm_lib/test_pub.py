from zenoh_comm import ZenohClient
import time

def main():
    client = ZenohClient()

    key = "demo/charging_station"

    print("🟢 Publisher running...")
    i = 0
    try:
        while True:
            msg = f"hello zenoh {i}"
            client.pub(key, msg.encode())
            i += 1
            time.sleep(1)
    except KeyboardInterrupt:
        print("❌ Publisher stopped")
        client.close()

if __name__ == "__main__":
    main()