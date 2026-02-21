"""
stepper_tb6600.py
Điều khiển động cơ bước TB6600 trên Raspberry Pi dùng pigpio
Port từ code C (stepper_tb6600.c) sang Python
"""

import pigpio
import threading
import time
import math
import logging
from typing import Callable, Any, Optional

# Cấu hình logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("STEPPER")

# Constants
MIN_FREQ_HZ = 100
MAX_FREQ_HZ = 40000
ACCEL_TIMER_PERIOD_MS = 10
PWM_DUTY = 512          # 50% duty cycle (10-bit: 512/1023)
PWM_DUTY_RES = 10       # 10-bit resolution

class StepperDirection:
    CW = 1
    CCW = 0

class StepperMicrostep:
    FULL = 1
    HALF = 2
    QUARTER = 4
    EIGHTH = 8
    SIXTEENTH = 16
    THIRTY_SECOND = 32

class StepperMode:
    IDLE = 0
    POSITION = 1
    VELOCITY = 2

class StepperConfig:
    def __init__(
        self,
        pulse_pin: int,
        dir_pin: int,
        enable_pin: Optional[int] = None,
        steps_per_revolution: int = 200,
        microstep: int = StepperMicrostep.FULL,
        max_speed_rpm: int = 300,
        min_speed_rpm: int = 60,
        accel_auto: bool = True,
        accel_steps: int = 0,
        accel_percent: int = 30,  # 0-100%
        complete_cb: Optional[Callable[['StepperMotor', Any], None]] = None,
        user_data: Any = None
    ):
        self.pulse_pin = pulse_pin
        self.dir_pin = dir_pin
        self.enable_pin = enable_pin
        self.steps_per_revolution = steps_per_revolution
        self.microstep = microstep
        self.max_speed_rpm = max_speed_rpm
        self.min_speed_rpm = min_speed_rpm
        self.accel_auto = accel_auto
        self.accel_steps = accel_steps
        self.accel_percent = min(max(accel_percent, 0), 100)
        self.complete_cb = complete_cb
        self.user_data = user_data


class StepperMotor:
    def __init__(self, pi: pigpio.pi, config: StepperConfig):
        self.pi = pi
        self.config = config

        self.lock = threading.Lock()

        self.current_dir = StepperDirection.CW
        self.current_position: int = 0
        self.target_position: int = 0
        self.mode = StepperMode.IDLE
        self.is_enabled: bool = False
        self.current_speed_rpm: int = 0
        self.target_speed_rpm: int = 0
        self.steps_to_go: int = 0
        self.total_steps: int = 0
        self.effective_accel_steps: int = 0
        self.timer_running: bool = False
        self.stop_requested: bool = False
        self.manual_stop: bool = False

        # PWM setup (pigpio hardware PWM)
        self.pi.set_mode(config.pulse_pin, pigpio.OUTPUT)
        self.pi.set_PWM_frequency(config.pulse_pin, 5000)  # initial freq
        self.pi.set_PWM_range(config.pulse_pin, 1024)      # 10-bit
        self.pi.set_PWM_dutycycle(config.pulse_pin, 0)

        # Direction pin
        self.pi.set_mode(config.dir_pin, pigpio.OUTPUT)
        self.pi.write(config.dir_pin, self.current_dir)

        # Enable pin (nếu có)
        if config.enable_pin is not None:
            self.pi.set_mode(config.enable_pin, pigpio.OUTPUT)
            self.pi.write(config.enable_pin, 1)  # disabled by default (active low)

        # Timers (threading.Timer)
        self.step_timer: Optional[threading.Timer] = None
        self.accel_timer: Optional[threading.Timer] = None

        logger.info(
            f"Motor initialized: PULSE={config.pulse_pin}, DIR={config.dir_pin}, "
            f"EN={config.enable_pin}, Accel={'AUTO' if config.accel_auto else 'MANUAL'} "
            f"{config.accel_percent}%"
        )

    def _rpm_to_hz(self, rpm: int) -> int:
        if rpm == 0:
            return MIN_FREQ_HZ
        hz = int((rpm * self.config.steps_per_revolution * self.config.microstep) / 60)
        return max(MIN_FREQ_HZ, min(MAX_FREQ_HZ, hz))

    def _start_pwm(self, freq_hz: int) -> bool:
        freq_hz = max(MIN_FREQ_HZ, min(MAX_FREQ_HZ, freq_hz))
        self.pi.set_PWM_frequency(self.config.pulse_pin, freq_hz)
        self.pi.set_PWM_dutycycle(self.config.pulse_pin, PWM_DUTY)
        logger.debug(f"PWM started at {freq_hz} Hz")
        return True

    def _stop_pwm(self):
        self.pi.set_PWM_dutycycle(self.config.pulse_pin, 0)
        logger.debug("PWM stopped")

    @staticmethod
    def _cubic_ease_in_out(t: float) -> float:
        if t < 0.5:
            return 4.0 * t * t * t
        f = 2.0 * t - 2.0
        return 1.0 + 0.5 * f * f * f

    def _check_completion(self):
        with self.lock:
            if (self.mode == StepperMode.IDLE or self.stop_requested) and not self.manual_stop:
                self.timer_running = False
                self._stop_pwm()
                if self.accel_timer:
                    self.accel_timer.cancel()
                if self.step_timer:
                    self.step_timer.cancel()

                logger.info(f"✅ Complete. Final pos={self.current_position}")

                if self.config.complete_cb:
                    self.config.complete_cb(self, self.config.user_data)

    def _step_counter(self):
        with self.lock:
            if not self.timer_running:
                return

            if self.mode == StepperMode.POSITION:
                if self.steps_to_go > 0:
                    self.steps_to_go -= 1

                    if self.current_dir == StepperDirection.CW:
                        self.current_position += 1
                    else:
                        self.current_position -= 1

                    if self.steps_to_go == 0:
                        self.mode = StepperMode.IDLE
                        self.stop_requested = True
                        self.current_position = self.target_position
                        self.manual_stop = False
                        self._check_completion()

    def _accel_timer(self):
        with self.lock:
            if not self.timer_running or self.mode == StepperMode.IDLE:
                return

            new_speed = self.target_speed_rpm
            steps_done = self.total_steps - self.steps_to_go

            if self.mode == StepperMode.POSITION and self.effective_accel_steps > 0:
                if steps_done < self.effective_accel_steps:
                    t = steps_done / self.effective_accel_steps
                    eased = self._cubic_ease_in_out(t)
                    new_speed = int(self.config.min_speed_rpm +
                                    (self.target_speed_rpm - self.config.min_speed_rpm) * eased)
                elif self.steps_to_go <= self.effective_accel_steps:
                    t = self.steps_to_go / self.effective_accel_steps
                    eased = self._cubic_ease_in_out(t)
                    new_speed = int(self.config.min_speed_rpm +
                                    (self.target_speed_rpm - self.config.min_speed_rpm) * eased)

            if abs(new_speed - self.current_speed_rpm) > 2:
                self.current_speed_rpm = new_speed
                freq = self._rpm_to_hz(new_speed)
                self.pi.set_PWM_frequency(self.config.pulse_pin, freq)

                # Restart step timer with new period
                period_us = int(1000000 / freq)
                if self.step_timer:
                    self.step_timer.cancel()
                self.step_timer = threading.Timer(period_us / 1000000.0, self._step_counter)
                self.step_timer.start()

    def enable(self, en: bool):
        if self.config.enable_pin is not None:
            self.pi.write(self.config.enable_pin, 0 if en else 1)  # active low
        self.is_enabled = en
        logger.info(f"Motor {'enabled' if en else 'disabled'}")

    def set_direction(self, dir: int):
        with self.lock:
            self.current_dir = dir
            self.pi.write(self.config.dir_pin, dir)

    def move_steps(self, steps: int, rpm: int) -> bool:
        if steps == 0:
            return False

        rpm = min(max(rpm, self.config.min_speed_rpm), self.config.max_speed_rpm)

        logger.info(f"move_steps: steps={steps}, rpm={rpm}")

        self.set_direction(StepperDirection.CW if steps > 0 else StepperDirection.CCW)
        time.sleep(0.001)

        with self.lock:
            self.target_position = self.current_position + steps
            self.target_speed_rpm = rpm
            self.total_steps = abs(steps)
            self.steps_to_go = self.total_steps
            self.mode = StepperMode.POSITION
            self.stop_requested = False
            self.manual_stop = False

            half_journey = self.total_steps // 2
            accel_by_percent = (half_journey * self.config.accel_percent) // 200

            if self.config.accel_auto:
                if self.config.accel_percent == 0:
                    self.effective_accel_steps = 0
                    self.current_speed_rpm = rpm
                elif self.total_steps <= 10:
                    self.effective_accel_steps = 0
                    self.current_speed_rpm = self.config.min_speed_rpm
                else:
                    self.effective_accel_steps = accel_by_percent
                    max_accel = (self.total_steps * 40) // 100
                    self.effective_accel_steps = min(self.effective_accel_steps, max_accel)
                    self.effective_accel_steps = max(self.effective_accel_steps, 1)
                    self.current_speed_rpm = self.config.min_speed_rpm
            else:
                if self.config.accel_steps == 0:
                    self.effective_accel_steps = 0
                    self.current_speed_rpm = rpm
                elif self.total_steps <= 10:
                    self.effective_accel_steps = 0
                    self.current_speed_rpm = self.config.min_speed_rpm
                elif self.total_steps > self.config.accel_steps * 2:
                    self.effective_accel_steps = self.config.accel_steps
                    self.current_speed_rpm = self.config.min_speed_rpm
                else:
                    self.effective_accel_steps = accel_by_percent
                    max_accel = (self.total_steps * 40) // 100
                    self.effective_accel_steps = min(self.effective_accel_steps, max_accel)
                    self.effective_accel_steps = max(self.effective_accel_steps, 1)
                    self.current_speed_rpm = self.config.min_speed_rpm

        freq = self._rpm_to_hz(self.current_speed_rpm)
        self._start_pwm(freq)

        self.timer_running = True

        period_us = int(1000000 / freq)
        self.step_timer = threading.Timer(period_us / 1000000.0, self._step_counter)
        self.step_timer.start()

        if self.effective_accel_steps > 0:
            self.accel_timer = threading.Timer(ACCEL_TIMER_PERIOD_MS / 1000.0, self._accel_timer)
            self.accel_timer.start()

        return True

    def move_to(self, target: int, rpm: int) -> bool:
        if self.is_running():
            logger.warning("Motor running! Stopping first...")
            self.stop()
            time.sleep(0.2)

        steps = target - self.current_position
        logger.info(f"move_to: current={self.current_position}, target={target}, steps={steps}")

        if steps == 0:
            logger.warning("Already at target")
            return True

        return self.move_steps(steps, rpm)

    def run_continuous(self, rpm: int):
        if rpm == 0:
            return self.stop()

        abs_rpm = abs(rpm)
        abs_rpm = min(abs_rpm, self.config.max_speed_rpm)

        dir = StepperDirection.CW if rpm > 0 else StepperDirection.CCW
        self.set_direction(dir)
        time.sleep(0.001)

        with self.lock:
            self.mode = StepperMode.VELOCITY
            self.stop_requested = False
            self.manual_stop = False
            self.target_speed_rpm = abs_rpm
            self.current_speed_rpm = abs_rpm

        freq = self._rpm_to_hz(abs_rpm)
        self._start_pwm(freq)
        self.timer_running = True

        logger.info(f"run_continuous: rpm={rpm}")

    def stop(self):
        with self.lock:
            self.stop_requested = True
            self.manual_stop = True
            self.mode = StepperMode.IDLE
            self.timer_running = False

        if self.accel_timer:
            self.accel_timer.cancel()
        if self.step_timer:
            self.step_timer.cancel()
        time.sleep(0.01)
        self._stop_pwm()

        logger.info(f"Motor stopped at {self.current_position}")

    def is_running(self) -> bool:
        with self.lock:
            return self.mode != StepperMode.IDLE

    def get_position(self) -> int:
        with self.lock:
            return self.current_position

    def set_position(self, pos: int):
        with self.lock:
            self.current_position = pos
            self.target_position = pos
        logger.info(f"Position set to {pos}")

    def close(self):
        self.stop()
        time.sleep(0.1)
        if self.accel_timer:
            self.accel_timer.cancel()
        if self.step_timer:
            self.step_timer.cancel()
        logger.info("Motor closed")

