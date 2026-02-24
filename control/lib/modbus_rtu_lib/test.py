"""
test.py
File kiểm tra nhanh thư viện modbus_rtu_master.py
"""

import time
from modbus_rtu import ModbusRtuMaster, ModbusMasterConfig


def on_data_received(slave_addr: int, func_code: int, reg_addr: int, data: list, length: int):
    print(f"→ Nhận dữ liệu từ slave {slave_addr} | FC {func_code:02x} | "
          f"Addr {reg_addr} | Data: {data} (length={length})")


def main():
    # Cấu hình – thay đổi theo thiết bị thật của bạn
    config = ModbusMasterConfig(
        port="/dev/ttyS0",       # hoặc "/dev/serial0", "/dev/ttyAMA0"
        baudrate=9600,
        parity="N",
        timeout=1.0,
        # rts_pin=18,             
    )

    master = ModbusRtuMaster(config)

    if not master.init():
        print("Khởi tạo Modbus thất bại. Kiểm tra port, baudrate, kết nối.")
        return

    # Đăng ký callback (tùy chọn)
    master.register_callback(on_data_received)

    print("Modbus RTU Master đang chạy... Nhấn Ctrl+C để thoát")

    try:
        while True:
            # Ví dụ đọc Holding Registers (FC 0x03)
            data = master.read_holding_registers(slave_addr=1, reg_addr=0, count=5)
            if data:
                print(f"Holding Registers (slave 1, addr 0): {data}")

            # Ví dụ viết Single Register (FC 0x06)
            success = master.write_single_register(slave_addr=1, reg_addr=10, value=999)
            print(f"Write single register thành công? {success}")

            # Ví dụ đọc Coils (FC 0x01)
            coils = master.read_coils(slave_addr=1, coil_addr=0, count=8)
            if coils:
                print(f"Coils (slave 1, addr 0): {coils}")

            time.sleep(3)  # Đọc mỗi 3 giây

    except KeyboardInterrupt:
        print("\nĐã thoát bằng Ctrl+C")
    except Exception as e:
        print(f"Lỗi trong quá trình chạy: {e}")
    finally:
        master.deinit()
        print("Đã dọn dẹp Modbus Master")


if __name__ == "__main__":
    main()