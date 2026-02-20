"""
limit_switch.py
Thư viện Limit Switch (công tắc hành trình / nút nhấn) cho Raspberry Pi sử dụng pigpio
- Hỗ trợ debounce bằng timer
- Callback khi trạng thái thay đổi sau debounce
- Hỗ trợ active HIGH hoặc active LOW
- Đọc trạng thái bất kỳ lúc nào qua is_pressed()
"""

import pigpio
import threading
from typing import Optional, Callable, Any
from enum import Enum


class LimitSwitchEvent(Enum):
    """Các sự kiện có thể xảy ra với limit switch"""
    PRESSED = 0
    RELEASED = 1


class LimitSwitch:
    """
    Limit Switch (công tắc hành trình / nút nhấn) với debounce và callback.
    
    Đặc điểm:
    - Debounce bằng timer (không busy-wait)
    - Callback chỉ gọi khi trạng thái THỰC SỰ thay đổi sau debounce
    - Tự động cấu hình pull-up/pull-down phù hợp
    - Có thể kiểm tra trạng thái bất kỳ lúc nào
    """

    def __init__(
        self,
        pi: pigpio.pi,
        pin: int,
        active_high: bool = False,
        debounce_ms: int = 50,
        callback: Optional[Callable[['LimitSwitch', LimitSwitchEvent, Any], None]] = None,
        user_data: Any = None
    ):
        """
        Khởi tạo Limit Switch.

        Args:
            pi: pigpio.pi instance (phải kết nối trước)
            pin: số GPIO (Broadcom numbering)
            active_high: True nếu nút nhấn mức cao khi kích hoạt
            debounce_ms: thời gian debounce (ms), mặc định 50ms
            callback: hàm gọi khi trạng thái thay đổi
            user_data: dữ liệu tùy ý truyền vào callback
        """
        self.pi = pi
        self.pin = pin
        self.active_high = active_high
        self.debounce_ms = max(debounce_ms, 1)
        self.callback = callback
        self.user_data = user_data

        self._last_pressed: bool = False
        self._debouncing: bool = False
        self._debounce_timer: Optional[threading.Timer] = None
        self._pigpio_cb: Optional[pigpio.callback] = None

        self._setup_gpio()
        self._read_initial_state()
        self._register_interrupt()

        print(f"[LimitSwitch] Khởi tạo GPIO{self.pin} | "
              f"active={'HIGH' if active_high else 'LOW'} | "
              f"debounce={self.debounce_ms}ms")

    def _setup_gpio(self) -> None:
        self.pi.set_mode(self.pin, pigpio.INPUT)
        if self.active_high:
            self.pi.set_pull_up_down(self.pin, pigpio.PUD_DOWN)
        else:
            self.pi.set_pull_up_down(self.pin, pigpio.PUD_UP)

    def _read_initial_state(self) -> None:
        level = self.pi.read(self.pin)
        self._last_pressed = (level == 1) if self.active_high else (level == 0)

    def _register_interrupt(self) -> None:
        self._pigpio_cb = self.pi.callback(
            self.pin,
            pigpio.EITHER_EDGE,
            self._on_edge
        )

    def _on_edge(self, gpio: int, level: int, tick: int) -> None:
        if not self._debouncing:
            self._debouncing = True
            self._debounce_timer = threading.Timer(
                self.debounce_ms / 1000.0,
                self._on_debounce_timeout
            )
            self._debounce_timer.start()

    def _on_debounce_timeout(self) -> None:
        self._debouncing = False
        level = self.pi.read(self.pin)
        current_pressed = (level == 1) if self.active_high else (level == 0)

        if current_pressed != self._last_pressed:
            self._last_pressed = current_pressed
            if self.callback:
                event = LimitSwitchEvent.PRESSED if current_pressed else LimitSwitchEvent.RELEASED
                self.callback(self, event, self.user_data)

    def is_pressed(self) -> bool:
        return self._last_pressed

    def release(self) -> None:
        if self._pigpio_cb:
            self._pigpio_cb.cancel()
            self._pigpio_cb = None

        if self._debounce_timer:
            self._debounce_timer.cancel()
            self._debounce_timer = None

        self.pi.set_pull_up_down(self.pin, pigpio.PUD_OFF)
        print(f"[LimitSwitch] Đã giải phóng GPIO{self.pin}")

    def __del__(self):
        self.release()