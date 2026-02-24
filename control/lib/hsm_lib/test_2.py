"""
main.py - Test logic HSM trên Python (tương đương main.c đã giản hóa)
Chỉ giữ HSM + giả lập dispatch event từ "ngoài" (như nút nhấn, modbus, timer)
"""

import time
from typing import Any, Optional

from hsm import (
    Hsm, HsmState, HsmEvent, HsmResult,
    HsmEvent as HEVT,  # Để dùng HEVT_xxx giống C
    HISTORY
)

# ────────────────────────────────────────────────
# Định nghĩa event user (tương tự HEVT_ trong C)
# ────────────────────────────────────────────────
HEVT_BUTTON_START = HEVT.USER + 1
HEVT_BUTTON_STOP = HEVT.USER + 2
HEVT_BATTERY_OK = HEVT.USER + 3
HEVT_CHARGING_DONE = HEVT.USER + 4
HEVT_ERROR_OVER_TEMP = HEVT.USER + 10
HEVT_MASTER_GET_SLOT_DATA = HEVT.USER + 20   # Giả lập Modbus polling
HEVT_MASTER_SLOT_NOTCONNECTED = HEVT.USER + 21


# ────────────────────────────────────────────────
# Cấu trúc HSM cho mainboard (tương đương app_state_hsm_t)
# ────────────────────────────────────────────────
class AppStateHSM:
    def __init__(self):
        self.hsm = Hsm("ChargerHSM")
        
        # Có thể thêm dữ liệu trạng thái nếu cần
        self.slot_data_received = False
        self.error_count = 0


mainboard = AppStateHSM()


# ────────────────────────────────────────────────
# Handler cho các state (tương đương handler trong C)
# ────────────────────────────────────────────────

def root_handler(hsm: Hsm, event: int, data: Any) -> int:
    print(f"[Root] Nhận event: 0x{event:04x}")
    if event == HEVT_MASTER_SLOT_NOTCONNECTED:
        print("[Root] Slot không kết nối → chuyển sang Error")
        hsm.transition(error_state)
        return HEVT.NONE
    return HEVT.NONE


def idle_handler(hsm: Hsm, event: int, data: Any) -> int:
    if event == HEVT.ENTRY:
        print("→ Vào Idle: Hiển thị 'Ready', đèn LED chờ")
    
    if event == HEVT.EXIT:
        print("← Thoát Idle")
    
    if event == HEVT_BUTTON_START:
        print("[Idle] Nhấn START → chuyển sang PreCharge")
        hsm.transition(precharge_state)
        return HEVT.NONE
    
    return event  # lan lên Root


def charging_handler(hsm: Hsm, event: int, data: Any) -> int:
    if event == HEVT.ENTRY:
        print("→ Vào Charging: Bật relay chính, khởi động đo áp/dòng")
    
    if event == HEVT.EXIT:
        print("← Thoát Charging: Tắt relay, lưu log sạc")
    
    if event == HEVT_BUTTON_STOP:
        print("[Charging] Nhấn STOP → quay về Idle")
        hsm.transition(idle_state)
        return HEVT.NONE
    
    if event == HEVT_ERROR_OVER_TEMP:
        print("[Charging] Quá nhiệt → chuyển sang Error")
        hsm.transition(error_state)
        return HEVT.NONE
    
    if event == HEVT_MASTER_GET_SLOT_DATA:
        print("[Charging] Nhận dữ liệu slot từ Modbus → xử lý")
        mainboard.slot_data_received = True
        return HEVT.NONE
    
    return event  # lan lên Root


def precharge_handler(hsm: Hsm, event: int, data: Any) -> int:
    if event == HEVT.ENTRY:
        print("→ Vào PreCharge: Đo áp ban đầu, kiểm tra kết nối...")
    
    if event == HEVT.EXIT:
        print("← Thoát PreCharge")
    
    if event == HEVT_BATTERY_OK:
        print("[PreCharge] Pin OK → chuyển sang CC_Charging")
        hsm.transition(cc_charging_state)
        return HEVT.NONE
    
    return event  # lan lên Charging


def cc_charging_handler(hsm: Hsm, event: int, data: Any) -> int:
    if event == HEVT.ENTRY:
        print("→ Vào CC_Charging: Đặt dòng 10A, theo dõi áp tăng")
    
    if event == HEVT.EXIT:
        print("← Thoát CC_Charging")
    
    if event == HEVT_CHARGING_DONE:
        print("[CC_Charging] Đầy pin → hoàn tất, quay về Idle")
        hsm.transition(idle_state)
        return HEVT.NONE
    
    return event  # lan lên Charging


def error_handler(hsm: Hsm, event: int, data: Any) -> int:
    if event == HEVT.ENTRY:
        print("→ Vào Error: Bật đèn đỏ, buzzer, gửi cảnh báo")
        mainboard.error_count += 1
    
    if event == HEVT.EXIT:
        print("← Thoát Error: Reset buzzer")
    
    if event == HEVT_BUTTON_START:
        print("[Error] Nhấn START → thử reset về Idle")
        hsm.transition(idle_state)
        return HEVT.NONE
    
    return event  # lan lên Root


# ────────────────────────────────────────────────
# Khai báo các state (cây hierarchy)
# ────────────────────────────────────────────────
root_state = HsmState("Root", root_handler, None)

idle_state = HsmState("Idle", idle_handler, root_state)

charging_state = HsmState("Charging", charging_handler, root_state)
precharge_state = HsmState("PreCharge", precharge_handler, charging_state)
cc_charging_state = HsmState("CC_Charging", cc_charging_handler, charging_state)

error_state = HsmState("Error", error_handler, root_state)


# ────────────────────────────────────────────────
# Hàm giả lập dispatch event (tương đương callback trong C)
# ────────────────────────────────────────────────
def simulate_events():
    print("\n=== Bắt đầu giả lập sự kiện ===\n")

    time.sleep(2)
    print("Giả lập: Nhấn nút START")
    mainboard.hsm.dispatch(HEVT_BUTTON_START)

    time.sleep(2)
    print("Giả lập: Pin kết nối OK (từ Modbus hoặc kiểm tra)")
    mainboard.hsm.dispatch(HEVT_BATTERY_OK)

    time.sleep(2)
    print("Giả lập: Nhận dữ liệu slot từ Modbus polling")
    mainboard.hsm.dispatch(HEVT_MASTER_GET_SLOT_DATA)

    time.sleep(2)
    print("Giả lập: Phát hiện quá nhiệt")
    mainboard.hsm.dispatch(HEVT_ERROR_OVER_TEMP)

    time.sleep(2)
    print("Giả lập: Nhấn nút START để reset lỗi")
    mainboard.hsm.dispatch(HEVT_BUTTON_START)

    time.sleep(2)
    print("Giả lập: Nhấn nút STOP")
    mainboard.hsm.dispatch(HEVT_BUTTON_STOP)

    time.sleep(2)
    print("Giả lập: Sạc hoàn tất")
    mainboard.hsm.dispatch(HEVT_CHARGING_DONE)

    if HISTORY:
        time.sleep(2)
        print("Giả lập: Transition về history")
        mainboard.hsm.transition_history()

    print("\n=== Test HSM hoàn tất ===")
    print(f"Trạng thái cuối: {mainboard.hsm.get_current_state().name if mainboard.hsm.get_current_state() else 'None'}")


def main():
    print("=====================================")
    print("  Test logic HSM trên Python")
    print("  (không phần cứng, chỉ giả lập event)")
    print("=====================================\n")

    # Khởi tạo HSM (tương đương app_state_hsm_init)
    print("Khởi tạo HSM...")
    result = mainboard.hsm.init(idle_state)
    print(f"Khởi tạo HSM: {HsmResult(result).name}")
    print(f"Trạng thái ban đầu: {mainboard.hsm.get_current_state().name}")

    # Chạy giả lập sự kiện
    simulate_events()


if __name__ == "__main__":
    main()