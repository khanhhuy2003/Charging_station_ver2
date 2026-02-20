#pip install pymodbus - Install library for modbus RTU


"""
modbus_rtu_master.py
Modbus RTU Master cho Raspberry Pi (dùng pymodbus)
Tương đương modbus_master_manager trên ESP32
"""

import logging
from typing import Optional, Callable, List, Union
from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException
from pymodbus.pdu import ModbusResponse
from pymodbus.framer import ModbusRtuFramer

# Cấu hình logging (tương tự ESP_LOG)
logging.basicConfig()
log = logging.getLogger("MODBUS_MASTER")
log.setLevel(logging.INFO)


class ModbusMasterConfig:
    """Cấu hình Modbus Master (tương đương modbus_master_config_t)"""
    def __init__(
        self,
        port: str = "/dev/ttyUSB0",     # hoặc "/dev/serial0" nếu dùng GPIO UART
        baudrate: int = 9600,
        parity: str = "N",              # "N" none, "E" even, "O" odd
        bytesize: int = 8,
        stopbits: int = 1,
        timeout: float = 1.0,           # giây
        rts_pin: Optional[int] = None   # Nếu dùng GPIO để điều khiển DE/RE (MAX485)
    ):
        self.port = port
        self.baudrate = baudrate
        self.parity = parity
        self.bytesize = bytesize
        self.stopbits = stopbits
        self.timeout = timeout
        self.rts_pin = rts_pin          # Nếu cần toggle RTS thủ công


class ModbusRtuMaster:
    """
    Modbus RTU Master Manager
    - Tương đương modbus_master_manager trên ESP32
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
            GPIO.output(config.rts_pin, GPIO.LOW)  # mặc định receive

    def init(self) -> bool:
        """Khởi tạo Modbus Master - tương đương modbus_master_init"""
        if self.client is not None:
            log.warning("Modbus Master đã khởi tạo rồi")
            return True

        try:
            self.client = ModbusSerialClient(
                method="rtu",
                port=self.config.port,
                baudrate=self.config.baudrate,
                parity=self.config.parity,
                bytesize=self.config.bytesize,
                stopbits=self.config.stopbits,
                timeout=self.config.timeout,
                framer=ModbusRtuFramer,
                retries=3,
                strict=False,  # cho phép linh hoạt timing RS485
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
        """Giải phóng - tương đương modbus_master_deinit"""
        if self.client:
            self.client.close()
            self.client = None
        self._running = False
        log.info("Modbus RTU Master đã dừng")

        if self.config.rts_pin is not None:
            import RPi.GPIO as GPIO
            GPIO.cleanup()

    def register_callback(self, callback: Callable[[int, int, int, List[int], int], None]) -> None:
        """Đăng ký callback khi đọc dữ liệu thành công
        (slave_addr, reg_type, reg_addr, data, length)
        """
        self._callback = callback

    def is_running(self) -> bool:
        return self._running

    # ────────────────────────────────────────────────
    # Các hàm đọc/ghi - blocking, trả về True nếu OK
    # ────────────────────────────────────────────────

    def _call_callback(self, slave_addr: int, func_code: int, reg_addr: int, data: List[int]):
        if self._callback and data:
            self._callback(slave_addr, func_code, reg_addr, data, len(data))

    def read_holding_registers(self, slave_addr: int, reg_addr: int, count: int) -> Optional[List[int]]:
        """FC 0x03 - Read Holding Registers"""
        if not self.client:
            log.error("Modbus chưa khởi tạo")
            return None

        try:
            response = self.client.read_holding_registers(reg_addr, count, slave=slave_addr)
            if response.isError():
                log.error(f"Read holding error: {response}")
                return None

            values = response.registers
            self._call_callback(slave_addr, 0x03, reg_addr, values)
            return values
        except ModbusException as e:
            log.error(f"Lỗi read holding: {e}")
            return None

    def read_input_registers(self, slave_addr: int, reg_addr: int, count: int) -> Optional[List[int]]:
        """FC 0x04 - Read Input Registers"""
        if not self.client:
            return None
        try:
            response = self.client.read_input_registers(reg_addr, count, slave=slave_addr)
            if response.isError():
                log.error(f"Read input error: {response}")
                return None
            values = response.registers
            self._call_callback(slave_addr, 0x04, reg_addr, values)
            return values
        except ModbusException as e:
            log.error(f"Lỗi read input: {e}")
            return None

    def write_single_register(self, slave_addr: int, reg_addr: int, value: int) -> bool:
        """FC 0x06 - Write Single Register"""
        if not self.client:
            return False
        try:
            response = self.client.write_register(reg_addr, value, slave=slave_addr)
            return not response.isError()
        except ModbusException as e:
            log.error(f"Lỗi write single: {e}")
            return False

    def write_multiple_registers(self, slave_addr: int, reg_addr: int, values: List[int]) -> bool:
        """FC 0x10 - Write Multiple Registers"""
        if not self.client:
            return False
        try:
            response = self.client.write_registers(reg_addr, values, slave=slave_addr)
            return not response.isError()
        except ModbusException as e:
            log.error(f"Lỗi write multiple: {e}")
            return False

    def read_coils(self, slave_addr: int, coil_addr: int, count: int) -> Optional[List[bool]]:
        """FC 0x01 - Read Coils (trả về list bool)"""
        if not self.client:
            return None
        try:
            response = self.client.read_coils(coil_addr, count, slave=slave_addr)
            if response.isError():
                log.error(f"Read coils error: {response}")
                return None
            return response.bits[:count]
        except ModbusException as e:
            log.error(f"Lỗi read coils: {e}")
            return None

    def write_single_coil(self, slave_addr: int, coil_addr: int, value: bool) -> bool:
        """FC 0x05 - Write Single Coil"""
        if not self.client:
            return False
        try:
            response = self.client.write_coil(coil_addr, value, slave=slave_addr)
            return not response.isError()
        except ModbusException as e:
            log.error(f"Lỗi write coil: {e}")
            return False


# Ví dụ sử dụng nhanh (chạy file này trực tiếp để test)
if __name__ == "__main__":
    config = ModbusMasterConfig(
        port="/dev/ttyUSB0",    # thay bằng port thật của bạn
        baudrate=9600,
        parity="N",
        timeout=1.0
    )

    master = ModbusRtuMaster(config)
    if not master.init():
        print("Khởi tạo thất bại")
        exit(1)

    def on_data_received(slave, func, addr, data, length):
        print(f"Nhận dữ liệu từ slave {slave} | FC {func:02x} | Addr {addr} | Data: {data}")

    master.register_callback(on_data_received)

    # Test đọc holding registers
    data = master.read_holding_registers(slave_addr=1, reg_addr=0, count=5)
    if data:
        print("Holding registers:", data)

    # Test viết single register
    success = master.write_single_register(slave_addr=1, reg_addr=10, value=1234)
    print("Write single OK?" , success)

    master.deinit()