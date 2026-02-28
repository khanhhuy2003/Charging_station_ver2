"""
stepper_tb6600_wave.py  –  v3.0  (Wave / DMA edition)
=======================================================
Điều khiển động cơ bước TB6600 trên Raspberry Pi dùng pigpio WAVE.

Tại sao dùng Wave thay PWM?
────────────────────────────
  • PWM chỉ phát tần số cố định; thay tần số giữa chừng gây giật.
  • Wave cho phép định nghĩa chính xác từng xung (µs), phát qua DMA
    hoàn toàn độc lập với CPU / Python / GIL.
  • Acceleration/deceleration được nhúng thẳng vào dãy xung →
    không cần threading.Timer, không có jitter.

Kiến trúc Wave trong driver này:
──────────────────────────────────
  Một lần di chuyển gồm 3 wave segment:

    [ACCEL wave]  →  [CRUISE wave (lặp N lần)]  →  [DECEL wave]

  wave_chain() kết hợp chúng lại, phát bằng DMA.
  Một GPIO callback (RISING_EDGE) đếm step thực tế để cập nhật position.

Giới hạn pigpio wave:
──────────────────────
  • Tối đa 256 wave IDs cùng lúc → driver tự xóa wave cũ sau khi dùng.
  • wave_chain có cú pháp đặc biệt (xem _send_wave_chain).
  • Mỗi lần gọi wave_add_* cộng dồn vào buffer → phải wave_clear()
    trước khi xây wave mới.
"""

import pigpio
import threading
import time
import logging
from typing import Optional, Callable, Any, List

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("STEPPER_W")


# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────
MIN_RPM          = 10        # RPM tối thiểu tuyệt đối
MAX_RPM          = 600       # RPM tối đa tuyệt đối
PULSE_HIGH_US    = 5         # Độ rộng xung HIGH (µs) – TB6600 cần ≥ 2.5µs
MIN_STEP_US      = 25        # Tương đương ~40 000 Hz tối đa
MAX_STEP_PERIOD  = 100_000   # µs, tương đương 10 Hz (rất chậm)

# Số bước tối đa trong 1 wave segment
# pigpio giới hạn ~10 000 pulses / wave, ta chọn an toàn
MAX_PULSES_PER_WAVE = 8_000

# wave_chain loop syntax (pigpio)
# [wave_id, 255, 0]            → phát 1 lần
# [wave_id, 255, 1, lo, hi]   → lặp (hi<<8|lo) lần
WAVE_LOOP_MAX = 0xFFFF   # 65535 lần lặp tối đa trong 1 loop


# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────
class Dir:
    CW  = 1
    CCW = 0

class Microstep:
    FULL          = 1
    HALF          = 2
    QUARTER       = 4
    EIGHTH        = 8
    SIXTEENTH     = 16
    THIRTY_SECOND = 32

class Mode:
    IDLE     = 0
    POSITION = 1
    VELOCITY = 2


# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────
class StepperConfig:
    """
    Cấu hình trục động cơ bước.

    Args:
        pulse_pin       : BCM pin PULSE
        dir_pin         : BCM pin DIR
        enable_pin      : BCM pin EN (None nếu không dùng)
        steps_per_rev   : Step/vòng (thường 200)
        microstep       : Vi bước đặt trên TB6600
        max_speed_rpm   : Tốc độ tối đa (RPM)
        min_speed_rpm   : Tốc độ khởi đầu tăng tốc (RPM)
        accel_percent   : % hành trình dùng để tăng tốc (0–50)
                          VD: 30 → 30% đầu tăng tốc, 30% cuối giảm tốc
        accel_easing    : 'linear' | 'cubic' | 'scurve'
        auto_enable     : Tự enable/disable driver khi chạy/dừng
        complete_cb     : Callback(motor, user_data) khi hoàn thành
        user_data       : Dữ liệu tuỳ ý cho callback
    """
    def __init__(
        self,
        pulse_pin     : int,
        dir_pin       : int,
        enable_pin    : Optional[int]                             = None,
        steps_per_rev : int                                       = 200,
        microstep     : int                                       = Microstep.FULL,
        max_speed_rpm : int                                       = 300,
        min_speed_rpm : int                                       = 40,
        accel_percent : int                                       = 15,
        accel_easing  : str                                       = 'cubic',
        auto_enable   : bool                                      = True,
        complete_cb   : Optional[Callable[['StepperMotor', Any], None]] = None,
        user_data     : Any                                       = None,
    ):
        if not (0 < min_speed_rpm < max_speed_rpm):
            raise ValueError("Cần: 0 < min_speed_rpm < max_speed_rpm")
        if accel_easing not in ('linear', 'cubic', 'scurve'):
            raise ValueError("accel_easing phải là 'linear', 'cubic', hoặc 'scurve'")

        self.pulse_pin     = pulse_pin
        self.dir_pin       = dir_pin
        self.enable_pin    = enable_pin
        self.steps_per_rev = steps_per_rev
        self.microstep     = microstep
        self.max_speed_rpm = min(max_speed_rpm, MAX_RPM)
        self.min_speed_rpm = max(min_speed_rpm, MIN_RPM)
        self.accel_percent = max(0, min(accel_percent, 50))  # tối đa 50% mỗi chiều
        self.accel_easing  = accel_easing
        self.auto_enable   = auto_enable
        self.complete_cb   = complete_cb
        self.user_data     = user_data


# ─────────────────────────────────────────────
# Motor
# ─────────────────────────────────────────────
class StepperMotor:
    """
    Điều khiển TB6600 bằng pigpio Wave/DMA.

    Toàn bộ xung phát qua DMA (không tốn CPU).
    GPIO callback chỉ dùng để đếm step / cập nhật position.
    """

    def __init__(self, pi: pigpio.pi, config: StepperConfig):
        if not pi.connected:
            raise RuntimeError("pigpiod chưa chạy! Hãy chạy: sudo pigpiod")

        self.pi  = pi
        self.cfg = config

        self._lock     = threading.RLock()
        self._done     = threading.Event()
        self._done.set()  # ban đầu không có lệnh nào đang chạy

        # ── Trạng thái ──
        self._mode       : int  = Mode.IDLE
        self._dir        : int  = Dir.CW
        self._position   : int  = 0
        self._target_pos : int  = 0
        self._steps_total: int  = 0
        self._steps_done : int  = 0   # đếm bởi GPIO callback
        self._enabled    : bool = False

        # ── Wave IDs đang giữ (cần xóa sau khi dùng) ──
        self._wave_ids: List[int] = []

        # ── GPIO ──
        pi.set_mode(config.pulse_pin, pigpio.OUTPUT)
        pi.write(config.pulse_pin, 0)

        pi.set_mode(config.dir_pin, pigpio.OUTPUT)
        pi.write(config.dir_pin, self._dir)

        if config.enable_pin is not None:
            pi.set_mode(config.enable_pin, pigpio.OUTPUT)
            self._hw_enable(False)

        # ── GPIO callback đếm xung ──
        self._cb = pi.callback(
            config.pulse_pin,
            pigpio.RISING_EDGE,
            self._on_pulse
        )

        # ── Thread giám sát hoàn thành (wave_tx_busy) ──
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitor_stop = threading.Event()

        logger.info(
            f"[STEPPER_W] Init  PULSE={config.pulse_pin}  DIR={config.dir_pin}"
            f"  EN={config.enable_pin}  micro=1/{config.microstep}"
            f"  easing={config.accel_easing}  accel={config.accel_percent}%"
        )

    # ══════════════════════════════════════════
    # Private – GPIO
    # ══════════════════════════════════════════

    def _hw_enable(self, en: bool):
        """Enable pin active-LOW."""
        if self.cfg.enable_pin is not None:
            self.pi.write(self.cfg.enable_pin, 0 if en else 1)
        self._enabled = en

    # ══════════════════════════════════════════
    # Private – Easing functions
    # ══════════════════════════════════════════

    def _ease(self, t: float) -> float:
        """t ∈ [0,1] → [0,1] theo easing được chọn."""
        e = self.cfg.accel_easing
        if e == 'linear':
            return t
        elif e == 'cubic':
            # Cubic ease-in  (t < 0.5 → ease in, toàn bộ [0,1] → ease in)
            return t * t * t
        else:  # scurve – cubic ease-in-out
            if t < 0.5:
                return 4.0 * t * t * t
            f = 2.0 * t - 2.0
            return 1.0 + 0.5 * f * f * f

    def _rpm_to_period_us(self, rpm: float) -> int:
        """Chuyển RPM → chu kỳ 1 step (µs)."""
        if rpm <= 0:
            return MAX_STEP_PERIOD
        hz = rpm * self.cfg.steps_per_rev * self.cfg.microstep / 60.0
        period = int(1_000_000 / hz)
        return max(MIN_STEP_US, min(MAX_STEP_PERIOD, period))

    # ══════════════════════════════════════════
    # Private – Xây dựng Wave
    # ══════════════════════════════════════════

    def _make_pulse(self, period_us: int) -> List[pigpio.pulse]:
        """Tạo 1 xung: HIGH PULSE_HIGH_US + LOW (period - HIGH) µs."""
        high = PULSE_HIGH_US
        low  = max(PULSE_HIGH_US, period_us - high)
        pin_mask = 1 << self.cfg.pulse_pin
        return [
            pigpio.pulse(pin_mask, 0,        high),
            pigpio.pulse(0,        pin_mask, low ),
        ]

    def _build_ramp_pulses(
        self,
        n_steps  : int,
        rpm_start: float,
        rpm_end  : float,
    ) -> List[pigpio.pulse]:
        """
        Xây dãy xung cho n_steps bước, tốc độ thay đổi từ rpm_start → rpm_end
        theo đường easing đã chọn.
        """
        pulses = []
        for i in range(n_steps):
            if n_steps > 1:
                t = i / (n_steps - 1)
            else:
                t = 1.0
            eased   = self._ease(t)
            rpm_now = rpm_start + (rpm_end - rpm_start) * eased
            period  = self._rpm_to_period_us(rpm_now)
            pulses.extend(self._make_pulse(period))
        return pulses

    def _build_const_pulses(self, n_steps: int, rpm: float) -> List[pigpio.pulse]:
        """Xây dãy xung tốc độ không đổi."""
        period = self._rpm_to_period_us(rpm)
        one_step = self._make_pulse(period)
        return one_step * n_steps  # list nhân lên

    def _create_wave(self, pulses: List[pigpio.pulse]) -> int:
        """
        Nạp pulses vào pigpio, tạo wave và trả về wave_id.
        Gọi wave_clear() trước để reset buffer.
        QUAN TRỌNG: mỗi wave_create() cần 1 lần wave_clear + wave_add riêng.
        """
        self.pi.wave_add_generic(pulses)
        wave_id = self.pi.wave_create()
        if wave_id < 0:
            raise RuntimeError(
                f"wave_create thất bại (code {wave_id}). "
                "Có thể vượt quá giới hạn cb/pulse của pigpio."
            )
        return wave_id

    def _delete_old_waves(self):
        """Xóa tất cả wave IDs cũ để giải phóng tài nguyên."""
        for wid in self._wave_ids:
            try:
                self.pi.wave_delete(wid)
            except Exception:
                pass
        self._wave_ids.clear()

    def _build_and_send(
        self,
        accel_steps : int,
        cruise_steps: int,
        decel_steps : int,
        cruise_rpm  : float,
    ):
        """
        Xây 3 wave segment rồi dùng wave_chain phát.
        Mỗi segment là 1 wave ID riêng.

        wave_chain syntax pigpio:
          [wid]                    → phát 1 lần
          [255, 0, wid, 255, 1, lo, hi]  → lặp (hi<<8 | lo) lần
          kết thúc bằng [255, 0]
        """
        min_rpm = self.cfg.min_speed_rpm

        # ── Chia nhỏ nếu segment quá lớn (vượt MAX_PULSES_PER_WAVE) ──
        # Cruise segment có thể rất dài → dùng wave_chain loop

        chain = []
        self._delete_old_waves()
        self.pi.wave_clear()

        # 1. ACCEL wave
        if accel_steps > 0:
            pulses = self._build_ramp_pulses(accel_steps, min_rpm, cruise_rpm)
            wid_accel = self._create_wave(pulses)
            self._wave_ids.append(wid_accel)
            chain.append(wid_accel)   # phát 1 lần

        # 2. CRUISE wave (có thể lặp)
        if cruise_steps > 0:
            # Số bước mỗi lần lặp (không quá MAX_PULSES_PER_WAVE / 2 vì mỗi step = 2 pulses)
            steps_per_wave = min(cruise_steps, MAX_PULSES_PER_WAVE // 2)
            pulses = self._build_const_pulses(steps_per_wave, cruise_rpm)

            # Cần wave riêng → phải clear + add (KHÔNG clear wave accel đã tạo)
            # pigpio wave_clear xóa TẤT CẢ buffer chưa create → ta dùng cách:
            # sau wave_create, buffer đã "commit" vào wave ID, wave_clear reset buffer mới
            self.pi.wave_clear()      # reset buffer (không ảnh hưởng wave đã create)
            self.pi.wave_add_generic(pulses)
            wid_cruise = self.pi.wave_create()
            if wid_cruise < 0:
                raise RuntimeError(f"wave_create cruise thất bại: {wid_cruise}")
            self._wave_ids.append(wid_cruise)

            loops = cruise_steps // steps_per_wave
            remainder = cruise_steps % steps_per_wave

            if loops > 0:
                lo = loops & 0xFF
                hi = (loops >> 8) & 0xFF
                # wave_chain loop: [255, 0, wid, 255, 1, lo, hi]
                chain += [255, 0, wid_cruise, 255, 1, lo, hi]

            # Phần dư (nếu có) phát 1 lần
            if remainder > 0:
                self.pi.wave_clear()
                pulses_rem = self._build_const_pulses(remainder, cruise_rpm)
                self.pi.wave_add_generic(pulses_rem)
                wid_rem = self.pi.wave_create()
                if wid_rem < 0:
                    raise RuntimeError(f"wave_create remainder thất bại: {wid_rem}")
                self._wave_ids.append(wid_rem)
                chain.append(wid_rem)

        # 3. DECEL wave
        if decel_steps > 0:
            self.pi.wave_clear()
            pulses = self._build_ramp_pulses(decel_steps, cruise_rpm, min_rpm)
            self.pi.wave_add_generic(pulses)
            wid_decel = self.pi.wave_create()
            if wid_decel < 0:
                raise RuntimeError(f"wave_create decel thất bại: {wid_decel}")
            self._wave_ids.append(wid_decel)
            chain.append(wid_decel)

        # Kết thúc chain bằng [255, 0]... nhưng wave_chain pigpio Python
        # nhận list các wave_id (không phải raw bytes như C API).
        # Với Python binding: wave_chain([wid1, wid2, ...]) → phát tuần tự.
        # Để lặp: wave_chain([255, 0, wid, 255, 1, lo, hi, 255, 0])
        # → ta xây chain đúng format ở trên rồi thêm terminator.

        if chain:
            chain_cmd = []
            # Chuyển đổi: item là int → nếu < 256 thì có thể là wave_id hoặc lệnh
            # Với các wave_id phát 1 lần, wrap vào loop 1 lần cho nhất quán
            # HOẶC dùng cách đơn giản hơn cho wave_id thường:
            # pigpio Python wave_chain: list chứa wave IDs và control bytes

            # Build lại chain rõ ràng hơn:
            chain_cmd = self._build_chain_cmd(
                accel_steps, cruise_steps, decel_steps, cruise_rpm
            )
            self.pi.wave_chain(chain_cmd)

    def _build_chain_cmd(
        self,
        accel_steps : int,
        cruise_steps: int,
        decel_steps : int,
        cruise_rpm  : float,
    ) -> list:
        """
        Xây wave_chain command list theo đúng pigpio Python API.

        pigpio wave_chain Python format:
          - wave_id (int) : phát wave đó 1 lần
          - [255, 0]      : bắt đầu loop
          - [wave_id]     : wave bên trong loop
          - [255, 1, lo, hi] : lặp (hi<<8|lo) lần
        """
        cmd = []
        idx = 0  # index vào self._wave_ids

        # ACCEL
        if accel_steps > 0 and idx < len(self._wave_ids):
            cmd.append(self._wave_ids[idx])
            idx += 1

        # CRUISE loop
        if cruise_steps > 0 and idx < len(self._wave_ids):
            steps_per_wave = min(cruise_steps, MAX_PULSES_PER_WAVE // 2)
            loops     = cruise_steps // steps_per_wave
            remainder = cruise_steps % steps_per_wave

            if loops > 0:
                lo = loops & 0xFF
                hi = (loops >> 8) & 0xFF
                cmd += [255, 0, self._wave_ids[idx], 255, 1, lo, hi]
            idx += 1

            # Remainder wave
            if remainder > 0 and idx < len(self._wave_ids):
                cmd.append(self._wave_ids[idx])
                idx += 1

        # DECEL
        if decel_steps > 0 and idx < len(self._wave_ids):
            cmd.append(self._wave_ids[idx])
            idx += 1

        return cmd

    # ══════════════════════════════════════════
    # Private – Callback & Monitor
    # ══════════════════════════════════════════

    def _on_pulse(self, gpio, level, tick):
        """Pigpio GPIO callback – đếm mỗi xung RISING_EDGE."""
        with self._lock:
            if self._mode != Mode.POSITION:
                return

            self._steps_done += 1

            if self._dir == Dir.CW:
                self._position += 1
            else:
                self._position -= 1

    def _monitor_loop(self):
        """
        Thread giám sát wave_tx_busy.
        Khi wave phát xong → cập nhật state và gọi callback.
        """
        # Chờ wave bắt đầu phát (tránh race condition vừa gọi xong chưa kịp start)
        time.sleep(0.05)

        while not self._monitor_stop.is_set():
            busy = self.pi.wave_tx_busy()
            if not busy:
                break
            time.sleep(0.005)  # Poll mỗi 5ms

        with self._lock:
            if self._mode == Mode.POSITION:
                # Đồng bộ vị trí về target (tránh lệch do jitter đếm)
                self._position = self._target_pos
                self._mode     = Mode.IDLE

        if self.cfg.auto_enable:
            self._hw_enable(False)

        self._done.set()
        logger.info(f"[STEPPER_W] ✅ Hoàn thành. pos={self._position}")

        if self.cfg.complete_cb:
            try:
                self.cfg.complete_cb(self, self.cfg.user_data)
            except Exception as e:
                logger.error(f"[STEPPER_W] complete_cb lỗi: {e}")

    # ══════════════════════════════════════════
    # Private – Tính toán phân đoạn
    # ══════════════════════════════════════════

    def _calc_segments(self, total_steps: int, target_rpm: float):
        """
        Chia tổng số step thành 3 phân đoạn:
          accel_steps : tăng tốc (min_rpm → target_rpm)
          cruise_steps: tốc độ ổn định
          decel_steps : giảm tốc (target_rpm → min_rpm)
        """
        if self.cfg.accel_percent == 0 or total_steps <= 4:
            return 0, total_steps, 0

        accel = int(total_steps * self.cfg.accel_percent / 100)
        decel = accel
        cruise = total_steps - accel - decel

        if cruise < 0:
            # Tổng hành trình quá ngắn, chia đôi
            accel  = total_steps // 2
            decel  = total_steps - accel
            cruise = 0

        return accel, cruise, decel

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
            return self._mode != Mode.IDLE

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self, en: bool = True):
        self._hw_enable(en)
        logger.info(f"[STEPPER_W] {'Enabled' if en else 'Disabled'}")

    def set_direction(self, direction: int):
        with self._lock:
            self._dir = direction
            self.pi.write(self.cfg.dir_pin, direction)

    def set_position(self, pos: int):
        """Reset vị trí logic (không di chuyển motor)."""
        with self._lock:
            self._position   = pos
            self._target_pos = pos
        logger.info(f"[STEPPER_W] Position reset → {pos}")

    def move_steps(self, steps: int, rpm: Optional[int] = None) -> bool:
        """
        Di chuyển steps bước.
        steps > 0 : CW,  steps < 0 : CCW.
        rpm       : None → dùng max_speed_rpm của config.
        """
        if steps == 0:
            return False
        if self.is_running:
            logger.warning("[STEPPER_W] Motor đang chạy! Gọi stop() trước.")
            return False

        if rpm is None:
            rpm = self.cfg.max_speed_rpm
        rpm = float(max(self.cfg.min_speed_rpm, min(rpm, self.cfg.max_speed_rpm)))

        abs_steps = abs(steps)
        direction = Dir.CW if steps > 0 else Dir.CCW

        # Tính phân đoạn
        accel_steps, cruise_steps, decel_steps = self._calc_segments(abs_steps, rpm)

        with self._lock:
            self._target_pos  = self._position + steps
            self._steps_total = abs_steps
            self._steps_done  = 0
            self._mode        = Mode.POSITION
            self._done.clear()

        logger.info(
            f"[STEPPER_W] move_steps={steps}  rpm={rpm:.0f}"
            f"  accel={accel_steps}  cruise={cruise_steps}  decel={decel_steps}"
        )

        # Set direction
        self.set_direction(direction)
        time.sleep(0.001)  # DIR setup time

        if self.cfg.auto_enable:
            self._hw_enable(True)
            time.sleep(0.005)

        # Xây và phát wave
        try:
            self._build_and_send(accel_steps, cruise_steps, decel_steps, rpm)
        except Exception as e:
            logger.error(f"[STEPPER_W] Lỗi khi tạo wave: {e}")
            with self._lock:
                self._mode = Mode.IDLE
            self._done.set()
            return False

        # Khởi động monitor thread
        self._monitor_stop.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="wave-monitor"
        )
        self._monitor_thread.start()

        return True

    def move_to(self, target: int, rpm: Optional[int] = None) -> bool:
        """Di chuyển đến vị trí tuyệt đối."""
        with self._lock:
            steps = target - self._position

        if steps == 0:
            logger.info("[STEPPER_W] Đã ở vị trí mục tiêu.")
            return True

        logger.info(f"[STEPPER_W] move_to={target}  delta={steps}")
        return self.move_steps(steps, rpm)

    def run_continuous(self, rpm: int):
        """
        Chạy liên tục (velocity mode).
        Dùng wave_send_repeat với 1 wave ngắn.
        rpm > 0 → CW,  rpm < 0 → CCW,  rpm = 0 → stop().
        """
        if rpm == 0:
            return self.stop()
        if self.is_running:
            logger.warning("[STEPPER_W] Motor đang chạy! Gọi stop() trước.")
            return

        abs_rpm   = float(min(abs(rpm), self.cfg.max_speed_rpm))
        direction = Dir.CW if rpm > 0 else Dir.CCW

        self.set_direction(direction)
        time.sleep(0.001)

        # Tạo 1 wave ngắn rồi wave_send_repeat
        # Dùng 100 bước / wave để đủ dài tránh overhead
        chunk = 100
        pulses = self._build_const_pulses(chunk, abs_rpm)

        self._delete_old_waves()
        self.pi.wave_clear()
        self.pi.wave_add_generic(pulses)
        wid = self.pi.wave_create()
        if wid < 0:
            logger.error(f"[STEPPER_W] wave_create thất bại: {wid}")
            return
        self._wave_ids.append(wid)

        with self._lock:
            self._mode = Mode.VELOCITY
            self._done.clear()

        if self.cfg.auto_enable:
            self._hw_enable(True)
            time.sleep(0.005)

        self.pi.wave_send_repeat(wid)
        logger.info(f"[STEPPER_W] run_continuous rpm={rpm}")

    def stop(self):
        """Dừng motor ngay lập tức."""
        self._monitor_stop.set()
        self.pi.wave_tx_stop()

        with self._lock:
            prev_mode    = self._mode
            self._mode   = Mode.IDLE

        if self.cfg.auto_enable:
            self._hw_enable(False)

        self._done.set()
        self._delete_old_waves()

        if prev_mode != Mode.IDLE:
            logger.info(f"[STEPPER_W] Stopped at pos={self._position}")

    def wait_until_done(self, timeout: Optional[float] = None) -> bool:
        """
        Block cho đến khi hoàn thành (hoặc timeout giây).
        Trả về True nếu hoàn thành trước timeout, False nếu timeout.
        """
        return self._done.wait(timeout)

    def close(self):
        """Giải phóng tài nguyên. Gọi khi thoát chương trình."""
        self.stop()
        time.sleep(0.1)
        if self._cb:
            self._cb.cancel()
        self._delete_old_waves()
        logger.info("[STEPPER_W] Closed")


# ══════════════════════════════════════════════
# Demo
# ══════════════════════════════════════════════
if __name__ == "__main__":
    import sys

    def on_done(motor: StepperMotor, data):
        print(f"[CB] Xong! pos={motor.position}  data={data}")

    pi = pigpio.pi()
    if not pi.connected:
        print("❌ Không kết nối pigpiod. Hãy chạy: sudo pigpiod")
        sys.exit(1)

    cfg = StepperConfig(
        pulse_pin     = 18,
        dir_pin       = 23,
        enable_pin    = 24,
        steps_per_rev = 200,
        microstep     = Microstep.EIGHTH,   # 1/8 → 1600 step/vòng
        max_speed_rpm = 300,
        min_speed_rpm = 40,
        accel_percent = 15,                  # 30% tăng tốc, 30% giảm tốc
        accel_easing  = 'linear',
        auto_enable   = True,
        complete_cb   = on_done,
        user_data     = "test",
    )

    motor = StepperMotor(pi, cfg)

    try:
        # ── Test 1: 1 vòng CW ──────────────────
        print("\n=== Test 1: 1 vòng CW (1600 steps) ===")
        motor.move_steps(1600, rpm=200)
        done = motor.wait_until_done(timeout=15)
        print(f"Kết quả: {'✅ Done' if done else '⏱ Timeout'}  pos={motor.position}")

        time.sleep(0.5)

        # # ── Test 2: Quay về 0 ──────────────────
        # print("\n=== Test 2: Quay về 0 ===")
        # motor.move_to(0, rpm=250)
        # done = motor.wait_until_done(timeout=15)
        # print(f"Kết quả: {'✅ Done' if done else '⏱ Timeout'}  pos={motor.position}")

        # time.sleep(0.5)

        # # ── Test 3: Chạy liên tục 3 giây ───────
        # print("\n=== Test 3: Velocity mode 3 giây ===")
        # motor.run_continuous(150)
        # time.sleep(3)
        # motor.stop()
        # print(f"Dừng tại pos={motor.position}")

        # # ── Test 4: Hành trình ngắn (10 steps) ─
        # print("\n=== Test 4: Hành trình ngắn 10 steps ===")
        # motor.move_steps(10, rpm=100)
        # motor.wait_until_done(timeout=5)
        # print(f"pos={motor.position}")

    except KeyboardInterrupt:
        print("\n⚠ Dừng bởi người dùng")
        motor.stop()
    finally:
        motor.close()
        pi.stop()
        print("Bye!")
