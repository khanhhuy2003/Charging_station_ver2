import pigpio
import threading
import time
import logging
from typing import Callable, Any, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("STEPPER")

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────
MIN_FREQ_HZ        = 100
MAX_FREQ_HZ        = 40_000
ACCEL_PERIOD_MS    = 10      # Chu kỳ cập nhật tốc độ (ms)
PWM_DUTY           = 512     # 50% duty cycle (10-bit)
PWM_RANGE          = 1024    # 10-bit PWM range


# ──────────────────────────────────────────────
# Enums / Constants classes
# ──────────────────────────────────────────────
class Dir:
    CW  = 1
    CCW = 0

class Microstep:
    FULL         = 1
    HALF         = 2
    QUARTER      = 4
    EIGHTH       = 8
    SIXTEENTH    = 16
    THIRTY_SECOND= 32

class Mode:
    IDLE     = 0
    POSITION = 1
    VELOCITY = 2


# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────
class StepperConfig:
    """
    Cấu hình cho một trục động cơ bước.

    Args:
        pulse_pin           : GPIO pin PULSE (BCM)
        dir_pin             : GPIO pin DIR   (BCM)
        enable_pin          : GPIO pin EN    (BCM), None nếu không dùng
        steps_per_rev       : Số step/vòng của motor (thường 200)
        microstep           : Hệ số vi bước đặt trên TB6600
        max_speed_rpm       : Tốc độ tối đa (RPM)
        min_speed_rpm       : Tốc độ khởi đầu khi tăng tốc (RPM)
        accel_auto          : True = tự tính accel_steps theo accel_percent
        accel_steps         : Số step tăng/giảm tốc (chỉ dùng khi accel_auto=False)
        accel_percent       : % hành trình dành cho tăng/giảm tốc (0-100)
        auto_enable         : Tự enable motor khi chạy, disable khi dừng
        complete_cb         : Hàm callback khi hoàn thành (motor, user_data)
        user_data           : Dữ liệu tuỳ ý truyền vào callback
    """
    def __init__(
        self,
        pulse_pin           : int,
        dir_pin             : int,
        enable_pin          : Optional[int]                            = None,
        steps_per_rev       : int                                      = 200,
        microstep           : int                                      = Microstep.FULL,
        max_speed_rpm       : int                                      = 300,
        min_speed_rpm       : int                                      = 60,
        accel_auto          : bool                                     = True,
        accel_steps         : int                                      = 0,
        accel_percent       : int                                      = 30,
        auto_enable         : bool                                     = True,
        complete_cb         : Optional[Callable[['StepperMotor', Any], None]] = None,
        user_data           : Any                                      = None,
    ):
        if min_speed_rpm >= max_speed_rpm:
            raise ValueError("min_speed_rpm phải nhỏ hơn max_speed_rpm")

        self.pulse_pin     = pulse_pin
        self.dir_pin       = dir_pin
        self.enable_pin    = enable_pin
        self.steps_per_rev = steps_per_rev
        self.microstep     = microstep
        self.max_speed_rpm = max_speed_rpm
        self.min_speed_rpm = min_speed_rpm
        self.accel_auto    = accel_auto
        self.accel_steps   = accel_steps
        self.accel_percent = max(0, min(100, accel_percent))
        self.auto_enable   = auto_enable
        self.complete_cb   = complete_cb
        self.user_data     = user_data


# ──────────────────────────────────────────────
# Motor
# ──────────────────────────────────────────────
class StepperMotor:
    def __init__(self, pi: pigpio.pi, config: StepperConfig):
        if not pi.connected:
            raise RuntimeError("pigpio chưa kết nối (pigpiod chưa chạy?)")

        self.pi     = pi
        self.cfg    = config
        # RLock cho phép cùng một thread acquire nhiều lần (tránh deadlock)
        self._lock  = threading.RLock()
        self._done  = threading.Event()   # set khi hoàn thành 1 lệnh move

        # ── Trạng thái nội bộ ──
        self._mode              : int  = Mode.IDLE
        self._dir               : int  = Dir.CW
        self._position          : int  = 0
        self._target_pos        : int  = 0
        self._steps_to_go       : int  = 0
        self._total_steps       : int  = 0
        self._accel_steps_eff   : int  = 0
        self._cur_rpm           : int  = 0
        self._tgt_rpm           : int  = 0
        self._running           : bool = False
        self._enabled           : bool = False

        # ── Timer tăng/giảm tốc ──
        self._accel_timer : Optional[threading.Timer] = None

        # ── GPIO setup ──
        pi.set_mode(config.pulse_pin, pigpio.OUTPUT)
        pi.set_PWM_range(config.pulse_pin, PWM_RANGE)
        pi.set_PWM_dutycycle(config.pulse_pin, 0)

        pi.set_mode(config.dir_pin, pigpio.OUTPUT)
        pi.write(config.dir_pin, self._dir)

        if config.enable_pin is not None:
            pi.set_mode(config.enable_pin, pigpio.OUTPUT)
            self._set_enable_pin(False)  # disabled by default

        # ── Callback đếm xung (RISING_EDGE) ──
        # Gọi mỗi khi có 1 xung PULSE → đếm step chính xác ở phần cứng
        self._cb = pi.callback(config.pulse_pin, pigpio.RISING_EDGE, self._on_pulse)

        logger.info(
            f"[STEPPER] Init PULSE={config.pulse_pin} DIR={config.dir_pin} "
            f"EN={config.enable_pin} micro={config.microstep} "
            f"accel={'AUTO' if config.accel_auto else 'MANUAL'} {config.accel_percent}%"
        )

    # ══════════════════════════════════════════
    # Private – GPIO helpers
    # ══════════════════════════════════════════

    def _set_enable_pin(self, en: bool):
        """Enable pin active-LOW."""
        if self.cfg.enable_pin is not None:
            self.pi.write(self.cfg.enable_pin, 0 if en else 1)

    def _rpm_to_hz(self, rpm: int) -> int:
        if rpm <= 0:
            return MIN_FREQ_HZ
        hz = int(rpm * self.cfg.steps_per_rev * self.cfg.microstep / 60)
        return max(MIN_FREQ_HZ, min(MAX_FREQ_HZ, hz))

    def _apply_pwm(self, freq_hz: int):
        freq_hz = max(MIN_FREQ_HZ, min(MAX_FREQ_HZ, freq_hz))
        self.pi.set_PWM_frequency(self.cfg.pulse_pin, freq_hz)
        self.pi.set_PWM_dutycycle(self.cfg.pulse_pin, PWM_DUTY)

    def _stop_pwm(self):
        self.pi.set_PWM_dutycycle(self.cfg.pulse_pin, 0)

    # ══════════════════════════════════════════
    # Private – Easing
    # ══════════════════════════════════════════

    @staticmethod
    def _ease(t: float) -> float:
        """Cubic ease-in-out, t ∈ [0,1] → [0,1]."""
        if t < 0.5:
            return 4.0 * t * t * t
        f = 2.0 * t - 2.0
        return 1.0 + 0.5 * f * f * f

    def _interpolate_rpm(self, t: float) -> int:
        """Nội suy RPM từ min→max (hoặc ngược lại) theo easing."""
        eased = self._ease(t)
        return int(self.cfg.min_speed_rpm +
                   (self._tgt_rpm - self.cfg.min_speed_rpm) * eased)

    # ══════════════════════════════════════════
    # Private – Callbacks
    # ══════════════════════════════════════════

    def _on_pulse(self, gpio, level, tick):
        with self._lock:
            if not self._running or self._mode != Mode.POSITION:
                return

            # Cập nhật vị trí
            if self._dir == Dir.CW:
                self._position += 1
            else:
                self._position -= 1

            self._steps_to_go -= 1

            if self._steps_to_go <= 0:
                # Hoàn thành – dừng PWM ngay trong callback
                self._steps_to_go = 0
                self._position    = self._target_pos
                self._running     = False
                self._mode        = Mode.IDLE
                self._stop_pwm()
                self._cancel_accel_timer()
                if self.cfg.auto_enable:
                    self._set_enable_pin(False)
                self._done.set()
                # Gọi callback trong thread riêng để không block pigpio
                if self.cfg.complete_cb:
                    threading.Thread(
                        target=self.cfg.complete_cb,
                        args=(self, self.cfg.user_data),
                        daemon=True
                    ).start()

    def _accel_tick(self):
        """
        Được gọi mỗi ACCEL_PERIOD_MS ms để cập nhật tốc độ theo profile.
        Tự reschedule cho đến khi dừng.
        """
        with self._lock:
            if not self._running or self._mode == Mode.IDLE:
                return

            if self._mode == Mode.POSITION and self._accel_steps_eff > 0:
                steps_done = self._total_steps - self._steps_to_go
                new_rpm = self._tgt_rpm

                # Giai đoạn tăng tốc
                if steps_done < self._accel_steps_eff:
                    t = steps_done / self._accel_steps_eff
                    new_rpm = self._interpolate_rpm(t)
                # Giai đoạn giảm tốc
                elif self._steps_to_go <= self._accel_steps_eff:
                    t = self._steps_to_go / self._accel_steps_eff
                    new_rpm = self._interpolate_rpm(t)

                new_rpm = max(self.cfg.min_speed_rpm, min(self._tgt_rpm, new_rpm))

                if abs(new_rpm - self._cur_rpm) > 1:
                    self._cur_rpm = new_rpm
                    self._apply_pwm(self._rpm_to_hz(new_rpm))

            elif self._mode == Mode.VELOCITY:
                # Velocity mode: giữ nguyên tốc độ đặt
                pass

        # Reschedule (bên ngoài lock để tránh giữ lock trong khi tạo timer)
        with self._lock:
            still_running = self._running

        if still_running:
            self._accel_timer = threading.Timer(
                ACCEL_PERIOD_MS / 1000.0, self._accel_tick
            )
            self._accel_timer.daemon = True
            self._accel_timer.start()

    def _cancel_accel_timer(self):
        if self._accel_timer:
            self._accel_timer.cancel()
            self._accel_timer = None

    # ══════════════════════════════════════════
    # Private – Tính toán acceleration
    # ══════════════════════════════════════════

    def _calc_accel_steps(self, total: int) -> int:
        """Trả về số step dành cho tăng/giảm tốc (mỗi chiều)."""
        if total <= 10:
            return 0

        half = total // 2

        if self.cfg.accel_auto:
            if self.cfg.accel_percent == 0:
                return 0
            # accel_percent % của nửa hành trình
            accel = (half * self.cfg.accel_percent) // 100
        else:
            if self.cfg.accel_steps == 0:
                return 0
            if total > self.cfg.accel_steps * 2:
                return self.cfg.accel_steps
            # Tổng hành trình ngắn → scale down
            accel = (half * self.cfg.accel_percent) // 100

        # Giới hạn tối đa 40% tổng hành trình (mỗi chiều)
        max_accel = (total * 40) // 100
        return max(1, min(accel, max_accel))

    # ══════════════════════════════════════════
    # Public API
    # ══════════════════════════════════════════

    @property
    def position(self) -> int:
        with self._lock:
            return self._position

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self, en: bool = True):
        """Bật/tắt driver TB6600 (enable pin active-LOW)."""
        self._set_enable_pin(en)
        self._enabled = en
        logger.info(f"[STEPPER] {'Enabled' if en else 'Disabled'}")

    def set_direction(self, direction: int):
        with self._lock:
            self._dir = direction
            self.pi.write(self.cfg.dir_pin, direction)

    def set_position(self, pos: int):
        """Đặt lại vị trí logic (không di chuyển motor)."""
        with self._lock:
            self._position   = pos
            self._target_pos = pos
        logger.info(f"[STEPPER] Position reset → {pos}")

    def move_steps(self, steps: int, rpm: int) -> bool:
        """
        Di chuyển một số bước nhất định.
        Âm = CCW, dương = CW.
        """
        if steps == 0:
            return False
        if self.is_running:
            logger.warning("[STEPPER] Đang chạy! Gọi stop() trước.")
            return False

        rpm = max(self.cfg.min_speed_rpm, min(rpm, self.cfg.max_speed_rpm))

        direction = Dir.CW if steps > 0 else Dir.CCW
        self.set_direction(direction)
        time.sleep(0.001)   

        abs_steps = abs(steps)
        accel_eff = self._calc_accel_steps(abs_steps)
        start_rpm = self.cfg.min_speed_rpm if accel_eff > 0 else rpm

        with self._lock:
            self._target_pos      = self._position + steps
            self._tgt_rpm         = rpm
            self._cur_rpm         = start_rpm
            self._total_steps     = abs_steps
            self._steps_to_go     = abs_steps
            self._accel_steps_eff = accel_eff
            self._mode            = Mode.POSITION
            self._running         = True
            self._done.clear()

        logger.info(
            f"[STEPPER] move_steps={steps} rpm={rpm} "
            f"accel_steps={accel_eff} start_rpm={start_rpm}"
        )

        if self.cfg.auto_enable:
            self._set_enable_pin(True)
            time.sleep(0.005)  # Cho driver sẵn sàng

        self._apply_pwm(self._rpm_to_hz(start_rpm))

        if accel_eff > 0:
            self._accel_timer = threading.Timer(
                ACCEL_PERIOD_MS / 1000.0, self._accel_tick
            )
            self._accel_timer.daemon = True
            self._accel_timer.start()

        return True

    def move_to(self, target: int, rpm: int) -> bool:
        """Di chuyển đến vị trí tuyệt đối."""
        with self._lock:
            steps = target - self._position

        if steps == 0:
            logger.info("[STEPPER] Đã ở vị trí mục tiêu.")
            return True

        logger.info(f"[STEPPER] move_to={target} (delta={steps})")
        return self.move_steps(steps, rpm)

    def run_continuous(self, rpm: int):
        """
        Chạy liên tục không giới hạn bước.
        rpm dương = CW, âm = CCW. rpm=0 → stop().
        """
        if rpm == 0:
            return self.stop()

        if self.is_running:
            logger.warning("[STEPPER] Đang chạy! Gọi stop() trước.")
            return

        abs_rpm   = min(abs(rpm), self.cfg.max_speed_rpm)
        direction = Dir.CW if rpm > 0 else Dir.CCW
        self.set_direction(direction)
        time.sleep(0.001)

        with self._lock:
            self._mode    = Mode.VELOCITY
            self._tgt_rpm = abs_rpm
            self._cur_rpm = abs_rpm
            self._running = True
            self._done.clear()

        if self.cfg.auto_enable:
            self._set_enable_pin(True)
            time.sleep(0.005)

        self._apply_pwm(self._rpm_to_hz(abs_rpm))
        logger.info(f"[STEPPER] run_continuous rpm={rpm}")

    def stop(self):
        """Dừng motor ngay lập tức."""
        with self._lock:
            was_running   = self._running
            self._running = False
            self._mode    = Mode.IDLE
            self._stop_pwm()
            self._cancel_accel_timer()

        if self.cfg.auto_enable:
            self._set_enable_pin(False)

        self._done.set()

        if was_running:
            logger.info(f"[STEPPER] Stopped at position={self._position}")

    def wait_until_done(self, timeout: Optional[float] = None) -> bool:
        """
        Block cho đến khi lệnh move hoàn thành (hoặc timeout).
        Trả về True nếu hoàn thành, False nếu timeout.
        """
        return self._done.wait(timeout)

    def set_speed(self, rpm: int):
        """
        Thay đổi tốc độ ngay lập tức (chỉ dùng trong velocity mode).
        """
        with self._lock:
            if self._mode != Mode.VELOCITY:
                logger.warning("[STEPPER] set_speed chỉ dùng trong velocity mode")
                return
            rpm = max(self.cfg.min_speed_rpm, min(abs(rpm), self.cfg.max_speed_rpm))
            self._tgt_rpm = rpm
            self._cur_rpm = rpm
            self._apply_pwm(self._rpm_to_hz(rpm))

    def close(self):
        """Giải phóng tài nguyên (gọi khi thoát chương trình)."""
        self.stop()
        time.sleep(0.05)
        if self._cb:
            self._cb.cancel()
        logger.info("[STEPPER] Closed")


# ══════════════════════════════════════════════
# Demo / Test
# ══════════════════════════════════════════════
if __name__ == "__main__":
    import sys

    def on_complete(motor: StepperMotor, data):
        print(f"[CB] Hoàn thành! Vị trí cuối: {motor.position}")

    pi = pigpio.pi()
    if not pi.connected:
        print("Không kết nối được pigpiod!")
        sys.exit(1)

    cfg = StepperConfig(
        pulse_pin      = 18,
        dir_pin        = 23,
        enable_pin     = 24,
        steps_per_rev  = 200,
        microstep      = Microstep.EIGHTH,
        max_speed_rpm  = 300,
        min_speed_rpm  = 40,
        accel_auto     = True,
        accel_percent  = 30,
        auto_enable    = True,
        complete_cb    = on_complete,
    )

    motor = StepperMotor(pi, cfg)

    try:
        print("=== Test 1: Di chuyển 1600 steps CW ===")
        motor.move_steps(64000, 600)
        motor.wait_until_done(timeout=15)

        time.sleep(0.5)

        print("=== Test 2: move_to vị trí 0 ===")
        motor.move_to(0, 600)
        motor.wait_until_done(timeout=15)

        time.sleep(0.5)

        # print("=== Test 3: Chạy liên tục 2 giây ===")
        # motor.run_continuous(150)
        # time.sleep(10)
        # motor.stop()

        # print(f"Vị trí cuối: {motor.position}")

    except KeyboardInterrupt:
        print("\nDừng bởi người dùng")
        motor.stop()
    finally:
        motor.close()
        pi.stop()

