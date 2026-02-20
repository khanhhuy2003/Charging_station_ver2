"""
test.py
File kiểm tra nhanh thư viện limit_switch.py
Chạy file này để test nút nhấn trên GPIO
"""

import pigpio
import time
from Limit_switch import LimitSwitch, LimitSwitchEvent


def on_change(switch: LimitSwitch, event: LimitSwitchEvent, data):
    status = "NHẤN" if event == LimitSwitchEvent.PRESSED else "NHẢ"
    print(f"→ GPIO{switch.pin} : {status}")


def main():
    pi = pigpio.pi()
    if not pi.connected:
        print("Không kết nối được pigpiod. Hãy chạy lệnh: sudo pigpiod")
        return

    # Tạo instance LimitSwitch
    switch = LimitSwitch(
        pi=pi,
        pin=17,                  # thay bằng GPIO bạn đang dùng
        active_high=False,       # active LOW – phổ biến nhất
        debounce_ms=25,
        callback=on_change
    )

    print("Đang theo dõi nút nhấn... Nhấn Ctrl+C để thoát")

    try:
        while True:
            time.sleep(0.5)
            # Bạn có thể in trạng thái hiện tại bất kỳ lúc nào
            # print("Trạng thái hiện tại:", "NHẤN" if switch.is_pressed() else "NHẢ")
    except KeyboardInterrupt:
        print("\nĐã thoát bằng Ctrl+C")
    finally:
        switch.release()
        pi.stop()


if __name__ == "__main__":
    main()