"""
led_pwm_pigpio.py
Điều khiển LED bằng PWM trên Raspberry Pi dùng pigpio
- Fade in/out mượt mà
- Điều chỉnh độ sáng thủ công qua input
"""

import pigpio
import time
import sys
import threading

# Cấu hình
LED_PIN = 18          # GPIO18 (hỗ trợ hardware PWM tốt nhất)
PWM_FREQ = 1000       # Tần số PWM (1000Hz là ổn cho LED)
PWM_RANGE = 1024      # Phạm vi duty cycle (0-1023)

# Khởi tạo pigpio
pi = pigpio.pi()
if not pi.connected:
    print("pigpiod chưa chạy. Chạy lệnh: sudo pigpiod")
    sys.exit(1)

# Cấu hình PWM cho LED
pi.set_mode(LED_PIN, pigpio.OUTPUT)
pi.set_PWM_frequency(LED_PIN, PWM_FREQ)
pi.set_PWM_range(LED_PIN, PWM_RANGE)
pi.set_PWM_dutycycle(LED_PIN, 0)  # Tắt LED ban đầu

print(f"LED PWM khởi tạo trên GPIO{LED_PIN} @ {PWM_FREQ}Hz, range 0-{PWM_RANGE-1}")

def set_brightness(brightness: int):
    """
    Đặt độ sáng LED (0-100%)
    """
    if brightness < 0:
        brightness = 0
    if brightness > 100:
        brightness = 100
    
    duty = int((brightness / 100.0) * (PWM_RANGE - 1))
    pi.set_PWM_dutycycle(LED_PIN, duty)
    print(f"Độ sáng: {brightness}% (duty={duty})")


def fade_in(duration: float = 3.0):
    """Tăng sáng từ 0% → 100% trong khoảng thời gian (giây)"""
    print(f"Bắt đầu fade-in trong {duration} giây...")
    steps = 100
    delay = duration / steps
    
    for i in range(steps + 1):
        brightness = i
        set_brightness(brightness)
        time.sleep(delay)
    print("Fade-in hoàn tất")


def fade_out(duration: float = 3.0):
    """Giảm sáng từ 100% → 0% trong khoảng thời gian (giây)"""
    print(f"Bắt đầu fade-out trong {duration} giây...")
    steps = 100
    delay = duration / steps
    
    for i in range(steps, -1, -1):
        brightness = i
        set_brightness(brightness)
        time.sleep(delay)
    print("Fade-out hoàn tất")


def fade_loop():
    """Chạy fade in → out lặp lại (demo)"""
    while True:
        fade_in(2.0)
        time.sleep(1)
        fade_out(2.0)
        time.sleep(1)


# Chạy fade loop trong thread riêng (để không chặn input)
fade_thread = threading.Thread(target=fade_loop, daemon=True)
fade_thread.start()

print("\nCác lệnh có thể dùng (nhập rồi Enter):")
print("  0-100     → Đặt độ sáng % (ví dụ: 75)")
print("  fadein    → Fade in mượt")
print("  fadeout   → Fade out mượt")
print("  stop      → Dừng fade loop và tắt LED")
print("  quit/exit → Thoát chương trình")
print("  (Enter trống để tiếp tục fade loop)")

try:
    while True:
        cmd = input("> ").strip().lower()
        
        if cmd in ["quit", "exit", "q"]:
            print("Thoát chương trình...")
            break
        
        elif cmd == "stop":
            fade_thread = None  # Dừng thread fade (daemon nên tự dừng khi main thoát)
            set_brightness(0)
            print("Đã dừng fade và tắt LED")
        
        elif cmd == "fadein":
            fade_in(2.0)
        
        elif cmd == "fadeout":
            fade_out(2.0)
        
        elif cmd.isdigit():
            brightness = int(cmd)
            set_brightness(brightness)
        
        elif cmd == "":
            # Enter trống → tiếp tục fade loop (không làm gì)
            pass
        
        else:
            print("Lệnh không hợp lệ. Thử lại (0-100, fadein, fadeout, stop, quit)")

except KeyboardInterrupt:
    print("\nDừng bằng Ctrl+C")

finally:
    # Cleanup
    set_brightness(0)
    pi.set_PWM_dutycycle(LED_PIN, 0)
    pi.stop()
    print("Đã dọn dẹp GPIO và pigpio")