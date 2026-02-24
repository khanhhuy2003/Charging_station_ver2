from typing import Any
from hsm import Hsm, HsmState, HsmEvent, HsmResult, HISTORY


# ────────────────────────────────────────────────
# Các event user-defined (nhiều event hơn)
# ────────────────────────────────────────────────
EVENT_BUTTON_START = HsmEvent.USER + 1      # Nút bắt đầu sạc
EVENT_BUTTON_STOP = HsmEvent.USER + 2       # Nút dừng sạc
EVENT_BATTERY_CONNECTED = HsmEvent.USER + 3 # Phát hiện pin kết nối
EVENT_BATTERY_DISCONNECTED = HsmEvent.USER + 4  # Pin ngắt kết nối
EVENT_TIMER_EXPIRED = HsmEvent.USER + 5     # Timer hết (ví dụ kiểm tra định kỳ)
EVENT_CHARGING_DONE = HsmEvent.USER + 6     # Sạc hoàn tất (đầy pin)
EVENT_OVER_TEMP = HsmEvent.USER + 10        # Lỗi quá nhiệt
EVENT_COMM_ERROR = HsmEvent.USER + 11       # Lỗi giao tiếp Modbus
EVENT_LOW_VOLTAGE = HsmEvent.USER + 12      # Lỗi áp thấp


# ────────────────────────────────────────────────
# Các handler cho state (ví dụ máy sạc xe điện với hierarchy phức tạp)
# ────────────────────────────────────────────────

def root_handler(hsm: Hsm, event: int, data: Any) -> int:
    """Handler cho Root - xử lý event chung toàn hệ thống (không lan lên đâu nữa)"""
    if event == EVENT_COMM_ERROR:
        print("[Root] Lỗi giao tiếp nghiêm trọng → chuyển sang Error")
        hsm.transition(comm_fail_state)
        return HsmEvent.NONE
    print(f"[Root] Event {event} không được xử lý ở bất kỳ state nào")
    return HsmEvent.NONE


def idle_handler(hsm: Hsm, event: int, data: Any) -> int:
    """Handler cho Idle - trạng thái chờ"""
    if event == HsmEvent.ENTRY:
        print("→ Vào Idle: Đèn LED chờ, hiển thị 'Ready'")
    
    if event == HsmEvent.EXIT:
        print("← Thoát Idle: Chuẩn bị bắt đầu sạc")
    
    if event == EVENT_BUTTON_START:
        print("[Idle] Nhấn Start → kiểm tra pin")
        hsm.transition(precharge_state)
        return HsmEvent.NONE
    
    if event == EVENT_BATTERY_CONNECTED:
        print("[Idle] Phát hiện pin → tự động bắt đầu")
        hsm.transition(precharge_state)
        return HsmEvent.NONE
    
    return event  # lan lên Root nếu không xử lý


def charging_handler(hsm: Hsm, event: int, data: Any) -> int:
    """Handler cho Charging (cha) - xử lý chung cho tất cả chế độ sạc"""
    if event == HsmEvent.ENTRY:
        print("→ Vào Charging: Bật relay chính, khởi động đo dòng áp, bật quạt")
        # Code: bật relay, start modbus polling...
    
    if event == HsmEvent.EXIT:
        print("← Thoát Charging: Tắt relay, dừng đo, lưu log sạc")
        # Code: tắt relay, lưu Wh...
    
    if event == EVENT_BUTTON_STOP:
        print("[Charging] Nhấn Stop → dừng sạc, quay về Idle")
        hsm.transition(idle_state)
        return HsmEvent.NONE
    
    if event == EVENT_OVER_TEMP:
        print("[Charging] Quá nhiệt → chuyển sang Error")
        hsm.transition(over_temp_state)
        return HsmEvent.NONE
    
    if event == EVENT_BATTERY_DISCONNECTED:
        print("[Charging] Pin ngắt → dừng sạc")
        hsm.transition(idle_state)
        return HsmEvent.NONE
    
    return event  # lan lên Root nếu không xử lý


def precharge_handler(hsm: Hsm, event: int, data: Any) -> int:
    """Handler cho PreCharge - trạng thái kiểm tra ban đầu (con của Charging)"""
    if event == HsmEvent.ENTRY:
        print("→ Vào PreCharge: Đo áp ban đầu, kiểm tra kết nối (5 giây)")
        # Giả sử start timer để kiểm tra
    
    if event == EVENT_TIMER_EXPIRED:
        print("[PreCharge] Kiểm tra xong, áp OK → chuyển sang CC_Charging")
        hsm.transition(cc_charging_state)
        return HsmEvent.NONE
    
    if event == EVENT_LOW_VOLTAGE:
        print("[PreCharge] Áp thấp → lỗi")
        hsm.transition(low_voltage_state)
        return HsmEvent.NONE
    
    return event  # lan lên Charging


def cc_charging_handler(hsm: Hsm, event: int, data: Any) -> int:
    """Handler cho CC_Charging - sạc dòng hằng (con của Charging)"""
    if event == HsmEvent.ENTRY:
        print("→ Vào CC_Charging: Đặt dòng 10A, theo dõi áp")
    
    if event == EVENT_CHARGING_DONE:
        print("[CC_Charging] Đầy 80% → chuyển sang CV_Charging")
        hsm.transition(cv_charging_state)
        return HsmEvent.NONE
    
    if event == EVENT_TIMER_EXPIRED:
        print("[CC_Charging] Kiểm tra định kỳ: áp tăng → OK")
        return HsmEvent.NONE
    
    return event  # lan lên Charging


def cv_charging_handler(hsm: Hsm, event: int, data: Any) -> int:
    """Handler cho CV_Charging - sạc áp hằng (con của Charging)"""
    if event == HsmEvent.ENTRY:
        print("→ Vào CV_Charging: Đặt áp 4.2V, giảm dòng dần")
    
    if event == EVENT_CHARGING_DONE:
        print("[CV_Charging] Đầy pin → quay về Idle")
        hsm.transition(idle_state)
        return HsmEvent.NONE
    
    return event  # lan lên Charging


def error_handler(hsm: Hsm, event: int, data: Any) -> int:
    """Handler cho Error (cha) - xử lý chung cho lỗi"""
    if event == HsmEvent.ENTRY:
        print("→ Vào Error: Bật đèn đỏ, buzzer kêu, gửi cảnh báo Modbus")
    
    if event == HsmEvent.EXIT:
        print("← Thoát Error: Reset buzzer, quay về Idle")
    
    if event == EVENT_BUTTON_START:
        print("[Error] Nhấn Start → thử reset lỗi")
        hsm.transition(idle_state)
        return HsmEvent.NONE
    
    return event  # lan lên Root


def over_temp_handler(hsm: Hsm, event: int, data: Any) -> int:
    """Handler cho OverTemp - lỗi quá nhiệt (con của Error)"""
    if event == HsmEvent.ENTRY:
        print("→ Vào OverTemp: Tắt nguồn, chờ nguội")
    
    if event == EVENT_TIMER_EXPIRED:
        print("[OverTemp] Nhiệt độ giảm → thử reset")
        hsm.transition(idle_state)
        return HsmEvent.NONE
    
    return event  # lan lên Error


def comm_fail_handler(hsm: Hsm, event: int, data: Any) -> int:
    """Handler cho CommFail - lỗi giao tiếp (con của Error)"""
    if event == HsmEvent.ENTRY:
        print("→ Vào CommFail: Thử reconnect Modbus")
    
    return event  # lan lên Error


def low_voltage_handler(hsm: Hsm, event: int, data: Any) -> int:
    """Handler cho LowVoltage - lỗi áp thấp (con của Error)"""
    if event == HsmEvent.ENTRY:
        print("→ Vào LowVoltage: Kiểm tra nguồn đầu vào")
    
    return event  # lan lên Error


# ────────────────────────────────────────────────
# Tạo cây state (hierarchy phức tạp)
# ────────────────────────────────────────────────
root = HsmState("Root", root_handler)

idle_state = HsmState("Idle", idle_handler, root)

charging_state = HsmState("Charging", charging_handler, root)
precharge_state = HsmState("PreCharge", precharge_handler, charging_state)
cc_charging_state = HsmState("CC_Charging", cc_charging_handler, charging_state)
cv_charging_state = HsmState("CV_Charging", cv_charging_handler, charging_state)

error_state = HsmState("Error", error_handler, root)
over_temp_state = HsmState("OverTemp", over_temp_handler, error_state)
comm_fail_state = HsmState("CommFail", comm_fail_handler, error_state)
low_voltage_state = HsmState("LowVoltage", low_voltage_handler, error_state)


# ────────────────────────────────────────────────
# Khởi tạo và test HSM
# ────────────────────────────────────────────────
def main():
    machine = Hsm("ChargerHSM")
    result = machine.init(idle_state)
    print(f"Khởi tạo: {HsmResult(result).name}")

    # Bắt đầu sạc
    print("\n--- Nhấn nút Start ---")
    machine.dispatch(EVENT_BUTTON_START)  # Idle → PreCharge

    # Kiểm tra pin OK (timer expired)
    print("\n--- Timer kiểm tra hết ---")
    machine.dispatch(EVENT_TIMER_EXPIRED)  # PreCharge → CC_Charging

    # Đầy 80% → chuyển CV
    print("\n--- Sạc đầy 80% ---")
    machine.dispatch(EVENT_CHARGING_DONE)  # CC_Charging → CV_Charging

    # Lỗi quá nhiệt
    print("\n--- Phát hiện quá nhiệt ---")
    machine.dispatch(EVENT_OVER_TEMP)      # CV_Charging → OverTemp

    # Reset lỗi bằng nút
    print("\n--- Nhấn nút Start để reset ---")
    machine.dispatch(EVENT_BUTTON_START)   # OverTemp → Idle

    # Lỗi giao tiếp
    print("\n--- Lỗi Modbus ---")
    machine.dispatch(EVENT_COMM_ERROR)     # Idle → CommFail (lan lên Root)

    if HISTORY:
        print("\n--- Transition về history (quay về Idle) ---")
        machine.transition_history()


if __name__ == "__main__":
    main()