"""
test_stepper.py
File test/demo thư viện stepper_tb6600.py
Chạy file này để kiểm tra động cơ bước
"""

import time
import pigpio
from Motor_control_TB6600 import StepperMotor, StepperConfig, StepperDirection

def on_complete(motor, data):
    print(f"Hoàn thành! Vị trí cuối: {motor.get_position()}")


def main():
    pi = pigpio.pi()
    if not pi.connected:
        print("pigpiod chưa chạy. Chạy lệnh: sudo pigpiod")
        return

    # Cấu hình motor (thay đổi pin theo board của bạn)
    config = StepperConfig(
        pulse_pin=17,          # GPIO17 - pulse
        dir_pin=27,            # GPIO27 - direction
        enable_pin=22,         # GPIO22 - enable (hoặc None nếu không dùng)
        steps_per_revolution=200,
        microstep=8,           # 1/8 microstep
        max_speed_rpm=300,
        min_speed_rpm=60,
        accel_auto=True,
        accel_percent=30,
        complete_cb=on_complete
    )

    motor = StepperMotor(pi, config)
    motor.enable(True)

    try:
        print("\n=== Test 1: Di chuyển đến vị trí 2000 bước ===")
        motor.move_to(2000, 150)
        while motor.is_running():
            time.sleep(0.2)
            print(f"Vị trí hiện tại: {motor.get_position()}")

        time.sleep(2)

        print("\n=== Test 2: Chạy liên tục 200 rpm trong 5 giây ===")
        motor.run_continuous(200)
        time.sleep(5)
        motor.stop()
        print(f"Dừng tại vị trí: {motor.get_position()}")

        time.sleep(2)

        print("\n=== Test 3: Di chuyển 5000 bước rồi dừng giữa chừng ===")
        motor.move_steps(5000, 120)
        time.sleep(3)  # Chạy 3 giây
        print("Dừng thủ công...")
        motor.stop()
        print(f"Dừng tại vị trí: {motor.get_position()}")

        time.sleep(2)

        print("\n=== Test 4: Reset vị trí về 0 và quay về 0 ===")
        motor.set_position(0)
        motor.move_to(0, 100)  # Không di chuyển vì đã ở 0
        time.sleep(1)

    except KeyboardInterrupt:
        print("\nDừng bằng Ctrl+C")

    finally:
        motor.close()
        pi.stop()
        print("Test hoàn tất")


if __name__ == "__main__":
    main()