# pip install pymodbus
#sudo chmod 666 /dev/ttyS0
"""
modbus_rtu_master.py
Modbus RTU Master cho Raspberry Pi (dùng pymodbus phiên bản mới nhất 3.x+)
Tương đương modbus_master_manager trên ESP32
"""
import logging
from typing import Optional, Callable, List

from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException
from pymodbus.framer import FramerType

# Cấu hình logging
logging.basicConfig()
log = logging.getLogger("MODBUS_MASTER")
log.setLevel(logging.INFO)


class ModbusMasterConfig:
    """Cấu hình Modbus Master"""
    def __init__(
        self,
        port: str = "/dev/serial0",          # hoặc "/dev/serial0" nếu dùng GPIO UART
        baudrate: int = 115200,
        parity: str = "N",                 # "N" none, "E" even, "O" odd
        bytesize: int = 8,
        stopbits: int = 1,
        timeout: float = 1.0,              # giây
        rts_pin: Optional[int] = None      # GPIO điều khiển DE/RE nếu cần
    ):
        self.port = port
        self.baudrate = baudrate
        self.parity = parity
        self.bytesize = bytesize
        self.stopbits = stopbits
        self.timeout = timeout
        self.rts_pin = rts_pin


class ModbusRtuMaster:
    """
    Modbus RTU Master Manager
    - Hỗ trợ callback khi đọc thành công (tùy chọn)
    """
    def __init__(self, config: ModbusMasterConfig):
        self.config = config
        self.client: Optional[ModbusSerialClient] = None
        self._callback: Optional[Callable[[int, int, int, List[int], int], None]] = None
        self._running = False

        # Nếu dùng RTS pin (GPIO điều khiển DE/RE)
        if config.rts_pin is not None:
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(config.rts_pin, GPIO.OUT)
            self._set_receive_mode()  # mặc định receive

    def _set_transmit_mode(self):
        if self.config.rts_pin is not None:
            import RPi.GPIO as GPIO
            GPIO.output(self.config.rts_pin, GPIO.HIGH)

    def _set_receive_mode(self):
        if self.config.rts_pin is not None:
            import RPi.GPIO as GPIO
            GPIO.output(self.config.rts_pin, GPIO.LOW)

    def init(self) -> bool:
        """Khởi tạo Modbus Master"""
        if self.client is not None:
            log.warning("Modbus Master đã khởi tạo rồi")
            return True

        try:
            self.client = ModbusSerialClient(
                port=self.config.port,
                framer=FramerType.RTU,
                baudrate=self.config.baudrate,
                parity=self.config.parity,
                bytesize=self.config.bytesize,
                stopbits=self.config.stopbits,
                timeout=self.config.timeout,
                retries=3,
            )
            if not self.client.connect():
                log.error(f"Không kết nối được Modbus RTU tại {self.config.port}")
                self.client = None
                return False

            self._running = True
            log.info(f"Modbus RTU Master khởi tạo OK | Port: {self.config.port} | Baud: {self.config.baudrate}")
            return True

        except Exception as e:
            log.error(f"Lỗi khởi tạo Modbus: {e}")
            self.client = None
            return False

    def deinit(self) -> None:
        """Giải phóng tài nguyên"""
        if self.client:
            self.client.close()
            self.client = None
        self._running = False
        log.info("Modbus RTU Master đã dừng")

        if self.config.rts_pin is not None:
            import RPi.GPIO as GPIO
            GPIO.cleanup()

    def register_callback(self, callback: Callable[[int, int, int, List[int], int], None]) -> None:
        """Đăng ký callback khi đọc dữ liệu thành công"""
        self._callback = callback

    def is_running(self) -> bool:
        return self._running

    def _call_callback(self, slave_addr: int, func_code: int, reg_addr: int, data: List[int]):
        if self._callback and data:
            self._callback(slave_addr, func_code, reg_addr, data, len(data))

    # ────────────────────────────────────────────────
    # Các hàm đọc/ghi - blocking
    # ────────────────────────────────────────────────

    def read_holding_registers(self, slave_addr: int, reg_addr: int, count: int) -> Optional[List[int]]:
        """FC 0x03 - Read Holding Registers"""
        if not self.client:
            log.error("Modbus chưa khởi tạo")
            return None

        self._set_transmit_mode()
        try:
            response = self.client.read_holding_registers(
                address=reg_addr,
                count=count,
                device_id=slave_addr
            )
            self._set_receive_mode()

            if response.isError():
                log.error(f"Read holding error: {response}")
                return None

            values = response.registers
            self._call_callback(slave_addr, 0x03, reg_addr, values)
            return values

        except ModbusException as e:
            self._set_receive_mode()
            log.error(f"Lỗi read holding: {e}")
            return None

    def read_input_registers(self, slave_addr: int, reg_addr: int, count: int) -> Optional[List[int]]:
        """FC 0x04 - Read Input Registers"""
        if not self.client:
            return None

        self._set_transmit_mode()
        try:
            response = self.client.read_input_registers(
                address=reg_addr,
                count=count,
                device_id=slave_addr
            )
            self._set_receive_mode()

            if response.isError():
                log.error(f"Read input error: {response}")
                return None

            values = response.registers
            self._call_callback(slave_addr, 0x04, reg_addr, values)
            return values

        except ModbusException as e:
            self._set_receive_mode()
            log.error(f"Lỗi read input: {e}")
            return None

    def write_single_register(self, slave_addr: int, reg_addr: int, value: int) -> bool:
        """FC 0x06 - Write Single Register"""
        if not self.client:
            return False

        self._set_transmit_mode()
        try:
            response = self.client.write_register(
                address=reg_addr,
                value=value,
                device_id=slave_addr
            )
            self._set_receive_mode()
            return not response.isError()

        except ModbusException as e:
            self._set_receive_mode()
            log.error(f"Lỗi write single: {e}")
            return False

    def write_multiple_registers(self, slave_addr: int, reg_addr: int, values: List[int]) -> bool:
        """FC 0x10 - Write Multiple Registers"""
        if not self.client:
            return False

        self._set_transmit_mode()
        try:
            response = self.client.write_registers(
                address=reg_addr,
                values=values,
                device_id=slave_addr
            )
            self._set_receive_mode()
            return not response.isError()

        except ModbusException as e:
            self._set_receive_mode()
            log.error(f"Lỗi write multiple: {e}")
            return False

    def read_coils(self, slave_addr: int, coil_addr: int, count: int) -> Optional[List[bool]]:
        """FC 0x01 - Read Coils"""
        if not self.client:
            return None

        self._set_transmit_mode()
        try:
            response = self.client.read_coils(
                address=coil_addr,
                count=count,
                device_id=slave_addr
            )
            self._set_receive_mode()

            if response.isError():
                log.error(f"Read coils error: {response}")
                return None

            return response.bits[:count]

        except ModbusException as e:
            self._set_receive_mode()
            log.error(f"Lỗi read coils: {e}")
            return None

    def write_single_coil(self, slave_addr: int, coil_addr: int, value: bool) -> bool:
        """FC 0x05 - Write Single Coil"""
        if not self.client:
            return False

        self._set_transmit_mode()
        try:
            response = self.client.write_coil(
                address=coil_addr,
                value=value,
                device_id=slave_addr
            )
            self._set_receive_mode()
            return not response.isError()

        except ModbusException as e:
            self._set_receive_mode()
            log.error(f"Lỗi write coil: {e}")
            return False