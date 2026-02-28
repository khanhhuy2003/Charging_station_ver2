import pigpio
import time


class SimpleStepper:

    def __init__(self, pi: pigpio.pi, step_pin: int, dir_pin: int, steps_per_rev: int = 200):
        # TODO 1:
        # - kiểm tra pi.connected
        # - lưu các biến cần thiết
        # - setup GPIO mode
        # - set PWM range = 1024
        # - set duty = 0 ban đầu
        
        pass


    def rpm_to_hz(self, rpm: float) -> float:
        # TODO 2:
        # công thức:
        # hz = rpm * steps_per_rev / 60
        pass


    def move_steps(self, steps: int, rpm: float):
        """
        Yêu cầu:
        - nếu steps = 0 -> return
        - set direction theo sign của steps
        - tính hz từ rpm
        - bật PWM với duty = 50%
        - sleep đủ thời gian để chạy hết số bước
        - sau đó stop()
        """

        # TODO 3
        pass


    def stop(self):
        # TODO 4:
        # set duty = 0
        pass