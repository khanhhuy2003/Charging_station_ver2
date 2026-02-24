# limit_switch.py
# Limit Switch Library using pigpio - Python port from ESP32 C library

import pigpio
import threading
from enum import IntEnum
from typing import Callable, Optional, Any


class LimitSwitchEvent(IntEnum):
    PRESSED = 0
    RELEASED = 1


# Type alias cho callback
LimitSwitchCallback = Callable[["LimitSwitch", LimitSwitchEvent, Any], None]


class LimitSwitch:
    def __init__(
        self,
        pi: pigpio.pi,
        gpio_pin: int,
        active_level: int = 0,
        debounce_ms: int = 50,
        callback: Optional[LimitSwitchCallback] = None,
        user_data: Any = None,
    ):
        """
        Khởi tạo limit switch.

        Args:
            pi:           Instance pigpio.pi đã kết nối
            gpio_pin:     GPIO pin number (BCM)
            active_level: Mức kích hoạt (0=LOW, 1=HIGH)
            debounce_ms:  Thời gian debounce (ms), mặc định 50
            callback:     Hàm callback(switch, event, user_data)
            user_data:    Dữ liệu tuỳ chọn truyền vào callback
        """
        if not pi.connected:
            raise RuntimeError("pigpio daemon không kết nối được")

        self._pi = pi
        self._gpio_pin = gpio_pin
        self._active_level = active_level
        self._debounce_ms = debounce_ms if debounce_ms > 0 else 50
        self._callback = callback
        self._user_data = user_data

        self._debouncing = False
        self._debounce_timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()

        # Cấu hình GPIO - tương đương gpio_config() trong ESP-IDF
        self._pi.set_mode(self._gpio_pin, pigpio.INPUT)

        if self._active_level == 0:
            # Active LOW → bật pull-up
            self._pi.set_pull_up_down(self._gpio_pin, pigpio.PUD_UP)
        else:
            # Active HIGH → bật pull-down
            self._pi.set_pull_up_down(self._gpio_pin, pigpio.PUD_DOWN)

        # Đọc trạng thái ban đầu
        level = self._pi.read(self._gpio_pin)
        self._last_state = level == self._active_level

        # Đăng ký ISR - tương đương gpio_isr_handler_add() + ANYEDGE
        self._cb_handle = self._pi.callback(
            self._gpio_pin,
            pigpio.EITHER_EDGE,
            self._isr_handler
        )

        print(f"[LIMIT_SWITCH] Initialized: GPIO{self._gpio_pin}, "
              f"active={self._active_level}, debounce={self._debounce_ms}ms")

    # ------------------------------------------------------------------
    # Private methods
    # ------------------------------------------------------------------

    def _isr_handler(self, gpio: int, level: int, tick: int):
        with self._lock:
            if not self._debouncing:
                self._debouncing = True
                # Bắt đầu debounce timer - tương đương esp_timer_start_once()
                self._debounce_timer = threading.Timer(
                    self._debounce_ms / 1000.0,
                    self._debounce_timer_callback
                )
                self._debounce_timer.daemon = True
                self._debounce_timer.start()

    def _debounce_timer_callback(self):
        level = self._pi.read(self._gpio_pin)
        pressed = (level == self._active_level)

        # Chỉ trigger callback nếu state thực sự thay đổi
        if pressed != self._last_state:
            self._last_state = pressed

            if self._callback:
                event = LimitSwitchEvent.PRESSED if pressed else LimitSwitchEvent.RELEASED
                self._callback(self, event, self._user_data)

        with self._lock:
            self._debouncing = False

    # ------------------------------------------------------------------
    # Public API - tương đương các hàm trong limit_switch.h
    # ------------------------------------------------------------------

    def is_pressed(self) -> bool:
        return self._last_state

    def deinit(self):

        # Huỷ debounce timer nếu đang chạy
        with self._lock:
            if self._debounce_timer and self._debounce_timer.is_alive():
                self._debounce_timer.cancel()
            self._debouncing = False

        # Huỷ đăng ký GPIO callback - tương đương gpio_isr_handler_remove()
        if self._cb_handle:
            self._cb_handle.cancel()
            self._cb_handle = None

        print(f"[LIMIT_SWITCH] Deinitialized: GPIO{self._gpio_pin}")

    def __del__(self):
        try:
            self.deinit()
        except Exception:
            pass

    def __repr__(self):
        return (f"LimitSwitch(gpio={self._gpio_pin}, "
                f"active_level={self._active_level}, "
                f"state={'PRESSED' if self._last_state else 'RELEASED'})")