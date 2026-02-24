# example.py
import pigpio
import time
from limit_switch import LimitSwitch, LimitSwitchEvent


def on_switch_event(switch: LimitSwitch, event: LimitSwitchEvent, user_data):
    name = user_data.get("name", "Unknown")
    if event == LimitSwitchEvent.PRESSED:
        print(f"[{name}] Switch PRESSED!")
    else:
        print(f"[{name}] Switch RELEASED!")


def main():
    pi = pigpio.pi()
    if not pi.connected:
        print("Lỗi: Không kết nối được pigpio daemon")
        print("Hãy chạy: sudo pigpiod")
        return

    # Khởi tạo limit switch trên GPIO17, active LOW (nối GND khi nhấn)
    switch = LimitSwitch(
        pi=pi,
        gpio_pin=17,
        active_level=0,
        debounce_ms=50,
        callback=on_switch_event,
        user_data={"name": "EndStop X"}
    )

    print(f"Trạng thái ban đầu: {switch}")

    try:
        while True:
            print(f"Pressed: {switch.is_pressed()}", end="\r")
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nDừng chương trình...")
    finally:
        switch.deinit()
        pi.stop()


if __name__ == "__main__":
    main()