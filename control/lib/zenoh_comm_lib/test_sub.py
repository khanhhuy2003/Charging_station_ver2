from zenoh_comm import ZenohClient
import time

count = 0

def on_data(sample):
    global count
    #raw = bytes(sample.payload)
    raw = sample.payload.to_string()
    count += 1
    print(
        f"📥 RECV {sample.key_expr}, data received: {raw} "
        f"=> bytes(length={len(raw)}), count={count}"
    )

def main():
    client = ZenohClient()

    # key = "demo/charging_station"
    key = "charger_1/charger/robot_request"
    client.sub(key, on_data)

    print("🟢 Subscriber running... Ctrl+C to stop")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("❌ Subscriber stopped")
        client.close()

if __name__ == "__main__":
    main()